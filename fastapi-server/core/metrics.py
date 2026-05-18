# core/metrics.py — FastAPI 비즈니스 레이어 커스텀 Prometheus 메트릭 레지스트리
#
# HTTP 수준 메트릭(_HTTP_REQUESTS_TOTAL 등)은 app.py에 있다.
# 이 파일은 비즈니스 도메인 메트릭만 다룬다.

from prometheus_client import Counter, Gauge, Histogram

# ── DRF 호출 실패 메트릭 ──────────────────────────────────────────────────────
# FastAPI → DRF POST 호출이 실패한 횟수.
# 이 값이 올라가면 가스/전력 데이터가 DRF에 저장되지 않은 것 — DRF 서버 상태와 함께 확인.
#
# 레이블:
#   error_type : "connect_error" — DRF에 TCP 연결 자체 실패
#                "timeout"       — DRF 응답 시간 초과
#                "http_error"    — 기타 httpx.HTTPError
#                "http_4xx"      — DRF 4xx 응답 (요청 오류)
#                "http_5xx"      — DRF 5xx 응답 (서버 오류)
DRF_CALL_FAILED_TOTAL = Counter(
    "fastapi_drf_call_failed_total",
    "Total DRF call failures from FastAPI (network errors and HTTP error responses)",
    ["error_type"],
)

# ── WS 알람 큐 길이 메트릭 ────────────────────────────────────────────────────
# Redis LIST `diconai:ws:alarms`에 쌓인 알람 수를 push/pop 시점마다 갱신한다.
# 이 값이 꾸준히 쌓이면 alarm_flush_loop가 소화 못 하는 것 — WS 연결 상태와 함께 확인.
# (Grafana alert 권장값: 100 이상이 5분 이상 지속이면 WS 브로드캐스트 병목 점검)
#
# multiprocess_mode="liveall":
#   향후 FastAPI multi-worker 전환 시 합산이 아닌 최신값이 노출되도록 명시.
ALARM_QUEUE_LENGTH = Gauge(
    "fastapi_alarm_queue_length",
    "Number of alarms waiting in the Redis WS alarm queue (diconai:ws:alarms)",
    multiprocess_mode="liveall",
)

# ── E2E 알람 latency 메트릭 (C7 — 운영 KPI) ──────────────────────────────────
# IoT 데이터가 FastAPI에 도착한 순간부터 브라우저 WS로 알람이 전송되는 순간까지.
# 전체 경로: FastAPI 수신 → DRF 저장 → Celery 알람 태스크 → FastAPI WS 전송.
#
# ingress_ts(float, Unix time)를 페이로드에 실어 각 서비스 경계를 통과시키고,
# alarm_flush_loop에서 now - ingress_ts 를 측정한다.
#
# 운영 SLO: p95 ≤ 1.5s. 초과 시 Celery worker 병목 또는 DB 락 의심.
E2E_ALARM_LATENCY = Histogram(
    "e2e_alarm_latency_seconds",
    "End-to-end alarm latency from IoT ingress at FastAPI to WebSocket send",
    buckets=[0.1, 0.25, 0.5, 1.0, 1.5, 3.0, 5.0, 10.0],
)
