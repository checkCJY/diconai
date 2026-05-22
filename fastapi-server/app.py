# app.py — FastAPI 통합 앱 진입점
#
# 도메인별 라우터(gas, power, positioning, websocket)를 한 곳에 등록한다.
# 실행: uvicorn app:app --reload --port 8001
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import settings
from core.logging import setup_logging
from core.redis_client import close_redis
from ai.router import router as ai_router
from gas.routers.gas_router import router as gas_router
from internal.routers.alarm_router import router as internal_alarm_router
from internal.routers.scenario_router import router as internal_scenario_router
from positioning.routers.position_router import router as positioning_router
from power.routers.power_router import router as power_router
from power.services.channel_meta_cache import channel_meta_refresh_loop
from power.services.threshold_sync import refresh_threshold_meta, threshold_sync_loop
from websocket.routers.ws_router import (
    alarm_flush_loop,
    broadcast_loop,
    router as ws_router,
)


setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"[app] action=startup log_level={settings.LOG_LEVEL} "
        f"broadcast_interval={settings.BROADCAST_INTERVAL_SEC}s"
    )
    # [M-8] 요청 수락 전에 전력 임계치를 1회 즉시 로드한다.
    # threshold_sync_loop 만 띄우면 create_task→yield 사이 첫 요청이 빈 캐시로
    # 처리될 수 있다. 실패해도 loop 가 backoff 재시도하므로 startup 을 막지 않는다.
    await refresh_threshold_meta()
    task1 = asyncio.create_task(
        broadcast_loop()
    )  # 센서 통합 페이로드 주기 브로드캐스트
    task2 = asyncio.create_task(alarm_flush_loop())  # 신규 알람 즉시 플러시
    task3 = asyncio.create_task(
        channel_meta_refresh_loop()
    )  # PowerDevice.channel_meta 5분 주기 동기화
    # T4 D1b — DRF power_facility_default threshold 5분 sync (단일 결정자 진입).
    task4 = asyncio.create_task(threshold_sync_loop())
    try:
        yield
    finally:
        task1.cancel()
        task2.cancel()
        task3.cancel()
        task4.cancel()
        await close_redis()  # Phase 1 C4 — Redis 연결 풀 정리
        logger.info("[app] action=shutdown")


app = FastAPI(
    title="DiconAI Realtime API",
    version="1.0.0",
    description=(
        "산재 예방 통합 관제 시스템의 실시간 처리 서버.\n\n"
        "**역할**:\n"
        "- IoT 센서(가스/전력/위치) 데이터 인입 및 검증\n"
        "- DRF 서버(:8000)로 영속화 위임\n"
        "- 브라우저로 WebSocket 실시간 브로드캐스트 (1초 주기)\n"
        "- Celery 태스크와의 알람 브리지 (`/internal/alarms/push/`)\n\n"
        "**데이터 흐름**: `IoT → FastAPI(:8001) → DRF(:8000) / 브라우저 WS`\n\n"
        "**관련 문서**: [API 명세](../docs/api_specification.md), "
        "[응답 봉투 표준](../docs/api_response_convention.md)"
    ),
    openapi_tags=[
        {"name": "sensors", "description": "가스 센서 HTTP 인입 (IoT 장비 → FastAPI)"},
        {"name": "power", "description": "전력 센서 HTTP 인입 (IoT 장비 → FastAPI)"},
        {"name": "positioning", "description": "작업자 위치 인입 (IoT/더미 → FastAPI)"},
        {"name": "websocket", "description": "브라우저용 실시간 스트림 (WS)"},
        {
            "name": "internal",
            "description": "서비스 간 통신 (Celery → FastAPI 브리지). localhost 전용",
        },
        {"name": "health", "description": "헬스체크"},
        {"name": "ai", "description": "IF 이상탐지 추론 (STEP B)"},
    ],
    lifespan=lifespan,
)

# 대시보드(DRF :8000) → FastAPI(:8001) 시연 컨트롤 fetch 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(gas_router)
app.include_router(power_router)
app.include_router(positioning_router)
app.include_router(ws_router)
app.include_router(internal_alarm_router)  # Celery → WS 브리지 (localhost 전용)
app.include_router(internal_scenario_router)  # 시연 시나리오 모드 컨트롤
app.include_router(ai_router)  # IF 이상탐지 추론 (STEP B)


# ── Prometheus 메트릭 (직접 노출, 외부 instrumentator 패키지 미사용) ──
# label에 raw path를 쓰면 path-param이 많은 라우트(/ws/worker/{user_id}/)에서
# 카디널리티 폭발 → request.scope["route"].path (라우트 템플릿) 사용.
_HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
_HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)


@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    _HTTP_REQUESTS_TOTAL.labels(request.method, path, response.status_code).inc()
    _HTTP_REQUEST_DURATION.labels(request.method, path).observe(elapsed)
    return response


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ── 전역 예외 핸들러 ────────────────────────────────────────────
# 응답 봉투 표준(docs/api_response_convention.md): {error: {code, message, details?}}.
# drf-server의 apps.core.exceptions와 동일 정책.

_HTTP_CODE_FALLBACK = {
    400: "validation_failed",
    401: "authentication_required",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "throttled",
    500: "internal_error",
    502: "upstream_unavailable",
    503: "upstream_unavailable",
    504: "upstream_unavailable",
}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = _HTTP_CODE_FALLBACK.get(exc.status_code, "internal_error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_failed",
                "message": "요청 데이터 검증에 실패했습니다.",
                "details": exc.errors(),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        f"[unhandled_exception] path={request.url.path} method={request.method} exc={exc!r}"
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "서버 내부 오류가 발생했습니다.",
            }
        },
    )


@app.get("/health/", tags=["health"], summary="헬스체크")
async def health_check() -> dict[str, str]:
    """서버 생존 확인용 엔드포인트. Liveness probe 등 운영 모니터링에 사용."""
    return {"status": "ok"}
