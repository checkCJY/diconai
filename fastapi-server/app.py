# app.py — FastAPI 통합 앱 진입점
#
# 도메인별 라우터(gas, power, positioning, websocket)를 한 곳에 등록한다.
# 실행: uvicorn app:app --reload --port 8001
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import settings
from core.logging import setup_logging
from gas.routers.gas_router import router as gas_router
from internal.routers.alarm_router import router as internal_alarm_router
from positioning.routers.position_router import router as positioning_router
from power.routers.power_router import router as power_router
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
    task1 = asyncio.create_task(
        broadcast_loop()
    )  # 센서 통합 페이로드 주기 브로드캐스트
    task2 = asyncio.create_task(alarm_flush_loop())  # 신규 알람 즉시 플러시
    try:
        yield
    finally:
        task1.cancel()
        task2.cancel()
        logger.info("[app] action=shutdown")


app = FastAPI(title="DiconAI FastAPI Server", lifespan=lifespan)

app.include_router(gas_router)
app.include_router(power_router)
app.include_router(positioning_router)
app.include_router(ws_router)
app.include_router(internal_alarm_router)  # Celery → WS 브리지 (localhost 전용)


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


@app.get("/health/")
async def health_check():
    """서버 생존 확인용 엔드포인트."""
    return {"status": "ok"}
