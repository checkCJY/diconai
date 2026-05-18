# core/metrics.py — FastAPI 비즈니스 레이어 커스텀 Prometheus 메트릭 레지스트리
#
# HTTP 수준 메트릭(_HTTP_REQUESTS_TOTAL 등)은 app.py에 있다.
# 이 파일은 비즈니스 도메인 메트릭만 다룬다.

import time as _time

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
# 운영 SLO: danger p95 ≤ 1.5s. 초과 시 Celery worker 병목 또는 DB 락 의심.
# warning 알람은 countdown=3s 설계상 항상 3.5s 이상 — SLO 대상 아님.
#
# 레이블:
#   risk_level : "danger" | "warning" — 분리해야 danger SLO 임계치를 의미있게 걸 수 있음
E2E_ALARM_LATENCY = Histogram(
    "e2e_alarm_latency_seconds",
    "End-to-end alarm latency from IoT ingress at FastAPI to WebSocket send",
    ["risk_level"],
    buckets=[0.1, 0.25, 0.5, 1.0, 1.5, 3.0, 5.0, 10.0],
)

# ── 센서 마지막 수신 시각 메트릭 (P1) ─────────────────────────────────────────
# 센서에서 마지막으로 데이터가 들어온 Unix timestamp를 기록한다.
# Grafana에서 `time() - sensor_last_received_seconds`로 경과 시간을 계산하면
# 센서 통신 단절을 즉시 감지할 수 있다. (300초 이상 = 5분 이상 무응답)
#
# 레이블:
#   sensor_type : "gas" | "power"
#   sensor_id   : 센서/장비 식별자 (GasDevice.device_id, PowerDevice.device_id)
SENSOR_LAST_RECEIVED = Gauge(
    "sensor_last_received_seconds",
    "Unix timestamp of last data received from each sensor",
    ["sensor_type", "sensor_id"],
    multiprocess_mode="liveall",
)

# ── Redis 명령 실행시간 메트릭 (P1) ───────────────────────────────────────────
# LPUSH / BRPOP 명령 실행 시간을 Histogram으로 기록한다.
# E2E latency가 급등했을 때 Redis 병목 여부를 판단하는 근거로 사용한다.
#   e2e_alarm_latency 급등
#     → celery_task_duration 정상 + db_save_duration 정상
#     → redis_command_duration 급등 → Redis 병목 확정
#
# 레이블:
#   command : "lpush" | "brpop"
REDIS_COMMAND_DURATION = Histogram(
    "redis_command_duration_seconds",
    "Redis command execution time (lpush/brpop in alarm queue)",
    ["command"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5],
)

# ── WebSocket 연결 수 메트릭 (P2 전) ──────────────────────────────────────────
# 현재 연결된 WebSocket 수를 타입별로 추적한다.
# connect 시 +1, disconnect 시 -1. 갑자기 0이 되면 전체 연결 끊김 신호.
# E2E latency가 정상인데 알람이 안 뜰 때 연결 수 확인으로 원인 확정 가능.
#
# 레이블:
#   type : "sensor"   — 브라우저 실시간 데이터 스트림 (/ws/sensors/)
#          "worker"   — 작업자 개인 알림 (/ws/worker/{user_id}/)
#          "position" — IoT 위치 장비 (/ws/position/)
WS_CONNECTIONS = Gauge(
    "fastapi_ws_connections",
    "Number of active WebSocket connections by type",
    ["type"],
    multiprocess_mode="liveall",
)

# ── AI 추론 소요 시간 메트릭 (P2 전) ──────────────────────────────────────────
# IF(Isolation Forest) / ARIMA 추론 실행 시간을 기록한다.
# E2E latency 급등 시 "FastAPI 안에서 AI 추론이 느린 건지" 판단 근거.
# Celery, DB, Redis가 모두 정상인데 E2E가 높으면 여기를 확인한다.
#
# 레이블:
#   model_type : "gas_if" | "power_if"
AI_INFERENCE_DURATION = Histogram(
    "ai_inference_duration_seconds",
    "AI inference execution time (Isolation Forest predict + decision_function)",
    ["model_type"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0],
)

# ── AI 추론 실패 수 메트릭 (P2 전) ───────────────────────────────────────────
# AI 추론이 예외로 실패할 때마다 카운터를 올린다.
# 실패 시 서비스는 계속 동작하지만(silent fail) AI 없이 룰 기반으로만 알람이 발생한다.
# 카운터가 올라가면 AI가 꺼진 상태임을 즉시 Grafana에서 확인 가능.
#
# 레이블:
#   model_type : "gas_if" | "power_if"
#   reason     : "model_not_loaded" | "inference_error"
AI_INFERENCE_FAILED_TOTAL = Counter(
    "ai_inference_failed_total",
    "AI inference failures (model not loaded or exception during predict)",
    ["model_type", "reason"],
)
