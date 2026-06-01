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
# Redis Stream `diconai:ws:alarms`의 적체 길이(XLEN)를 push/read 시점마다 갱신한다.
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

# ── WS 알람 스트림 lag 메트릭 (LIST→Stream 전환) ──────────────────────────────
# 스트림 말단(가장 최근 entry)과 이 프로세스의 커서(alarm_flush_loop last_id)의
# 시간차(초). entry ID 의 ms 부분 차이로 계산한다 (XINFO 불필요).
# 평상시 ≈0. 이 replica 가 알람을 소화 못 하면 증가 → alarm_flush_loop 지연 신호.
#
# multiprocess_mode="liveall" + Prometheus 가 pod 별 스크랩 → 멀티레플리카 시
# replica 별 lag 이 자동 분리되어 "어느 replica 가 뒤처지나"가 바로 보인다.
ALARM_STREAM_LAG = Gauge(
    "fastapi_alarm_stream_lag_seconds",
    "Time gap (s) between stream tail and this process cursor in the WS alarm stream",
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
# XADD / XREAD 명령 실행 시간을 Histogram으로 기록한다.
# E2E latency가 급등했을 때 Redis 병목 여부를 판단하는 근거로 사용한다.
#   e2e_alarm_latency 급등
#     → celery_task_duration 정상 + db_save_duration 정상
#     → redis_command_duration 급등 → Redis 병목 확정
#
# 레이블:
#   command : "xadd"  — alarm 적재 (push_alarm 에서 측정)
#             "xread" — alarm 소비. BLOCK 대기시간이 섞여 무의미하므로 측정하지 않는다
#                       (옛 brpop 과 동일 이유, parity). 라벨 정의만 남겨둠.
REDIS_COMMAND_DURATION = Histogram(
    "redis_command_duration_seconds",
    "Redis command execution time (xadd/xread in alarm queue)",
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

# ── T4 D2 — AI 알람 broadcast latency (a 경로 제거 후 실측용) ──────────────────
# plan §10 위험 — (a) push_alarm 직접 호출 제거 후 broadcast latency 변화 추적.
# ingress_ts(IoT 수신 시각) → push_alarm 직전 시각 차이를 .observe(). E2E 메트릭과
# 다른 차원 (E2E 는 DRF Celery 경로 포함, 본 메트릭은 fastapi 안 단일 결정자 경로).
# >500ms 면 plan §10 의 "옵션 B 2단계 업그레이드" 검토 신호.
AI_BROADCAST_LATENCY = Histogram(
    "ai_broadcast_latency_seconds",
    "Time from IoT ingress to AI alarm push (T4 D2 single-decision path)",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)

# ── 전력 AI 모니터링 메트릭 (정휘훈 작업) ────────────────────────────────────
# 전력 AI 추론 흐름의 각 구간을 메트릭으로 관찰한다.
# "AI가 왜 안 움직이냐"는 질문이 왔을 때 Grafana만 보고 원인 구간을 특정하는 것이 목표.

# quality_guard skip 횟수 —
#   센서 불량(통신 단절/오버플로우/고착)으로 AI 윈도우 적재가 skip된 횟수.
#   이 카운터가 올라가면 데이터는 들어오는데 AI가 조용히 멈춰있는 상태.
#   reason 레이블로 어떤 종류의 불량인지 구분해 센서 점검 방향을 잡는다.
#
# 레이블:
#   reason : "comm_failure"        — 센서 통신 단절 (-1 또는 None)
#            "sensor_fault_overflow" — 물리적으로 말이 안 되는 큰 값
#            "sensor_fault_stuck"    — 30개가 전부 동일값 (센서 고착 고장)
POWER_AI_QUALITY_SKIP_TOTAL = Counter(
    "power_ai_quality_skip_total",
    "Number of power AI inference skips due to sensor data quality issues",
    ["reason"],
)

# rate limit 억제 횟수 —
#   같은 채널에서 60초 이내 재발화가 억제된 횟수.
#   "알람이 1번만 왔다"는 신고가 왔을 때 이 카운터를 보면 즉시 원인 확인 가능.
#   이 값이 높으면 이상이 지속되고 있지만 운영자에게 전달이 안 되는 상태.
POWER_AI_RATE_LIMITED_TOTAL = Counter(
    "power_ai_rate_limited_total",
    "Number of power AI alarms suppressed by rate limit (60s per channel)",
)

# 5축 발화 횟수 —
#   IF / ARIMA / Z-score / Change Point / 야간 가동 중 어느 축이 이상 판정에 기여했는지.
#   특정 axis 카운터만 비정상적으로 높으면 그 축이 과탐지하고 있는 것.
#   오탐 신고가 왔을 때 어느 임계값을 조정해야 할지 특정하는 근거로 사용.
#
# 레이블:
#   axis : "if"           — Isolation Forest 이상 판정
#          "arima"        — ARIMA 신뢰구간 이탈
#          "zscore"       — Z-score 3σ 초과
#          "change_point" — Change Point STABLE→SHIFT 전이
#          "night"        — 야간 가동 격상
POWER_AI_AXIS_FIRED_TOTAL = Counter(
    "power_ai_axis_fired_total",
    "Number of times each detection axis contributed to power AI anomaly judgment",
    ["axis"],
)

# 추론 실행 횟수 —
#   AI 추론이 실제로 실행된 횟수 (quality_guard / 윈도우 미충족 skip 이후).
#   sensor_last_received 갱신 횟수 대비 이 값이 낮으면 skip이 많다는 신호.
#   갑자기 0이 되면 FastAPI 재시작으로 윈도우가 초기화됐을 가능성.
POWER_AI_INFERENCE_TOTAL = Counter(
    "power_ai_inference_total",
    "Number of power AI inference executions (after quality_guard and window warmup)",
)

# 최종 판정 분포 —
#   5축 종합 후 나온 판정 결과(normal/caution/predict_warn/danger)가 각각 몇 번인지.
#   danger 비율이 90% 이상이면 AI가 너무 예민한 것, normal이 99% 이상이면 너무 둔한 것.
#   일주일치 추이를 보면 모델 재학습이 필요한 시점 판단 가능.
#
# 레이블:
#   combined : "normal" | "caution" | "predict_warn" | "danger"
POWER_AI_COMBINED_TOTAL = Counter(
    "power_ai_combined_total",
    "Distribution of power AI combined risk judgments",
    ["combined"],
)

# 실제 알람 발화 횟수 —
#   rate limit을 통과해서 실제로 Redis 큐까지 전달된 알람 횟수.
#   combined danger 횟수 대비 이 값이 낮으면 rate limit이 타이트하거나 전달 문제.
#   갑자기 0이 되면 추론은 되는데 브라우저에 안 닿는 상태 — Redis/WS 확인 필요.
#
# 레이블:
#   algorithm_source : "isolation_forest" | "arima" | "combined" | "zscore" |
#                      "change_point" | "night_abnormal"
POWER_AI_ALARM_FIRED_TOTAL = Counter(
    "power_ai_alarm_fired_total",
    "Number of power AI alarms actually fired (passed rate limit and sent to Redis queue)",
    ["algorithm_source"],
)

# ── 가스 AI 모니터링 메트릭 ────────────────────────────────────────────────────
# 가스 AI 추론 흐름의 각 구간을 메트릭으로 관찰한다.
# 전력 AI 메트릭과 동일한 설계 원칙 — "AI가 왜 안 움직이냐"를 Grafana만 보고 특정.

# 추론 실행 횟수 —
#   change point 감지 후 실제로 IF 추론이 실행된 횟수.
#   갑자기 0이 되면 change point가 감지 안 되거나 윈도우 미충족 상태.
GAS_AI_INFERENCE_TOTAL = Counter(
    "gas_ai_inference_total",
    "Number of gas AI inference executions (after change point detection and window warmup)",
)

# change point 감지 횟수 —
#   co/h2s/co2 중 하나라도 패턴 변화가 감지된 횟수.
#   이 값 대비 GAS_AI_INFERENCE_TOTAL이 낮으면 모델 미로드 등 skip이 많다는 신호.
GAS_CP_DETECTED_TOTAL = Counter(
    "gas_cp_detected_total",
    "Number of change point detections in gas sensor sliding window (co/h2s/co2)",
)

# rate limit 억제 횟수 —
#   AI가 이상 감지했지만 60초 이내 재발화라 억제된 횟수.
#   알람이 1번만 왔다는 신고 시 이 카운터 확인.
GAS_AI_RATE_LIMITED_TOTAL = Counter(
    "gas_ai_rate_limited_total",
    "Number of gas AI alarms suppressed by rate limit (60s per sensor)",
)

# 실제 알람 발화 횟수 —
#   rate limit 통과 후 실제로 DRF에 AlarmRecord가 생성된 횟수.
#   gas_type 레이블로 어느 가스가 트리거했는지 구분.
#
# 레이블:
#   gas_type  : "co" | "h2s" | "co2" (AI 발화 시 대표 가스)
#   risk_level: "danger" (가스 AI는 항상 danger로 발화)
GAS_AI_ALARM_FIRED_TOTAL = Counter(
    "gas_ai_alarm_fired_total",
    "Number of gas AI alarms actually fired (passed rate limit)",
    ["gas_type", "risk_level"],
)
