# apps/core/metrics.py — 비즈니스 레이어 커스텀 Prometheus 메트릭 레지스트리
#
# HTTP 수준 메트릭(PrometheusMiddleware, _HTTP_REQUESTS_TOTAL 등)은
# apps/core/prometheus.py 에 있다. 이 파일은 비즈니스 도메인 메트릭만 다룬다.
#
# ── 이 파일에 메트릭을 모으는 이유 ──────────────────────────────────────────
# 이전에는 알람 메트릭이 alerts/tasks.py 안에 선언되어 있었다.
# 메트릭이 여러 파일에 흩어지면:
#   - "어떤 메트릭이 있는지" 파악하려면 전체 파일을 뒤져야 한다
#   - 메트릭 이름 충돌(Counter 중복 등록 에러)을 방지하기 어렵다
#   - Grafana 대시보드 설계 시 단일 참조점이 없다
# → 모든 커스텀 비즈니스 메트릭을 여기에 선언하고, 각 도메인 파일은 import해서 사용한다.
#
# ── multiprocess 모드 안내 ──────────────────────────────────────────────────
# PROMETHEUS_MULTIPROC_DIR 환경변수 설정 시 prometheus_client가 각 프로세스
# (gunicorn 워커, celery-worker, celery-beat)의 메트릭을 파일로 저장한다.
# Counter/Histogram: 자동으로 전 프로세스 합산 → 추가 설정 불필요.
# Gauge: 합산이 아닌 "현재값"이어야 하므로 multiprocess_mode 명시 필수.
#   - "liveall": 모든 프로세스의 현재값을 그대로 노출 (beat 1개에서만 갱신하므로 적합)
#   - "all": 전 프로세스 합산 → 큐 길이는 합산이면 잘못된 값이 되므로 사용 안 함

from prometheus_client import Counter, Gauge, Histogram

# ── 알람 발송 메트릭 ──────────────────────────────────────────────────────────
# 원래 alerts/tasks.py에 선언되어 있던 메트릭. 비즈니스 메트릭이므로 여기로 이동.
# alerts/tasks.py는 이 파일에서 import해서 그대로 사용한다.

# 실제 WebSocket으로 발송된 알람 수 (dedupe · 쿨다운 필터 통과 후).
# AlarmRecord가 생성만 되고 event가 None인 중복 케이스는 카운트에서 제외된다.
# 레이블:
#   alarm_type : "gas_threshold" | "geofence_intrusion" | "power_overload"
#   risk_level : "warning" | "danger"
ALARM_FIRED_TOTAL = Counter(
    "alarm_fired_total",
    "Total alarm notifications pushed to WebSocket (deduped, passed cooldown)",
    ["alarm_type", "risk_level"],
)

# FastAPI /internal/alarms/push/ HTTP 호출이 실패한 횟수.
# 이 값이 올라가면 알람이 브라우저에 전달되지 않은 것 — FastAPI 서버 상태와 함께 확인.
# 네트워크 오류(RequestError)와 5xx 응답을 모두 포함한다.
# 레이블:
#   alarm_type : 실패한 알람 종류 (페이로드의 alarm_type 필드)
ALARM_WS_PUSH_FAILED_TOTAL = Counter(
    "alarm_ws_push_failed_total",
    "Total WebSocket alarm push failures (network error or 5xx from FastAPI)",
    ["alarm_type"],
)

# ── DB 저장 성공/실패 메트릭 ──────────────────────────────────────────────────
# GasData / PowerData 저장 시도를 result(ok/error)와 error_type 레이블로 추적한다.
#
# SQLite로 운영 중일 때 동시 쓰기(gunicorn + celery)가 증가하면
# "database is locked" OperationalError가 발생한다.
# 이 에러 빈도가 일정 수준을 넘으면 PostgreSQL 마이그레이션 타이밍으로 판단한다.
# (Grafana alert 권장값: db_locked 에러가 5분간 5회 이상이면 migration 검토)
#
# 레이블:
#   model      : "gas" | "power" — 어느 도메인 데이터인지 구분
#   result     : "ok" | "error"
#   error_type : ""(성공시), "db_locked"(SQLite 동시성 한계),
#                "integrity"(중복·FK 위반), "other"(그 외)
#                result="ok"면 항상 "" — label cardinality 낮게 유지
DB_SAVE_TOTAL = Counter(
    "drf_db_save_total",
    "DB save attempts: successes and failures by model and error type",
    ["model", "result", "error_type"],
)

# DB 저장 latency Histogram.
# DB_SAVE_TOTAL(성공/실패 여부)과 함께 쓰면 "저장은 되는데 느린가"를 구분할 수 있다.
# PG 전환 전후 동일 메트릭으로 비교하면 전환 효과를 수치로 증명할 수 있다.
# (SQLite p95 ≥ 50ms / PG p95 ≥ 20ms 이면 각각 이상 신호)
#
# 레이블:
#   model : "gas" | "power"
DB_SAVE_DURATION = Histogram(
    "db_save_duration_seconds",
    "DB save latency for GasData and PowerData (ORM create / bulk_create)",
    ["model"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0, 5.0],
)

# ── Celery 큐 길이 메트릭 ────────────────────────────────────────────────────
# Redis의 Celery 큐를 LLEN 명령으로 읽어 대기 중인 태스크 수를 기록한다.
# Celery Beat(queue_metrics_task)이 30초마다 갱신한다.
#
# 이 메트릭이 필요한 이유:
#   큐 길이가 꾸준히 쌓인다 = 태스크 생성 속도 > worker 처리 속도.
#   지금은 alarmz 태스크가 몰릴 때 celery worker가 1개이므로 병목이 숨어 있다.
#   큐 길이 추이를 보고 "worker 프로세스 추가" or "도메인별 전용 큐 분리" 시점을 결정.
#   (Grafana alert 권장값: 큐 길이 50 이상이 5분 이상 지속이면 worker 증설 검토)
#
# multiprocess_mode="liveall":
#   Gauge는 "현재 상태값"이므로 프로세스간 합산(sum)이 아닌 최신값을 노출해야 한다.
#   Beat 프로세스 1개에서만 갱신하므로 실질적으로 단일값이지만,
#   prometheus_client multiprocess 규칙을 명시적으로 따른다.
#
# 레이블:
#   queue : Redis 큐 이름. 기본값 "celery". 도메인 분리 시 "alarm", "position" 등 추가.
CELERY_QUEUE_LENGTH = Gauge(
    "celery_queue_length",
    "Number of tasks waiting in the Celery queue (Redis llen)",
    ["queue"],
    multiprocess_mode="liveall",
)

# ── 지오펜스 위험도 판정 시간 메트릭 ─────────────────────────────────────────
# 작업자가 지오펜스에 진입했을 때 "이 구역 안에 위험 센서가 있는지" 판정하는 데
# 걸린 시간을 히스토그램으로 기록한다. (_get_dangerous_sensors_in_geofence 함수)
#
# 이 함수는 GasSensor + PowerDevice 각각에 대해 DB 쿼리를 실행한다.
# DB 부하가 높을수록 이 latency가 늘어나므로 인프라 스케일 판단에 활용한다.
#
# 왜 Histogram인가 (Average가 아닌 이유):
#   산업 안전 도메인에서 알람 지연은 실제 사고로 이어질 수 있다.
#   평균(mean)은 이상치를 희석시키지만 p95/p99는 "가장 느린 1%~5%의 작업자가
#   겪는 지연"을 직접 나타낸다. 99번째 백분위 기준으로 SLO를 관리한다.
#
# buckets 설계 근거:
#   0.005s( 5ms): Redis 캐시 히트 수준 — 이상적 목표
#   0.010s(10ms): 인덱스 탄 단순 쿼리 예상 응답시간
#   0.050s(50ms): 복수 쿼리 + DB 경합 허용 범위 상한
#   0.100s(100ms): 알람 발화 허용 최대치 (SLO: p99 ≤ 100ms 목표)
#   0.500s(500ms): 명백한 병목 — 긴급 조치 필요 수준
#   1.000s, 5.000s: 장애 수준 이상치 캡처 (레코드만)
GEOFENCE_CHECK_DURATION = Histogram(
    "geofence_check_duration_seconds",
    "Time to check for dangerous sensors inside geofence (includes DB queries)",
    buckets=[0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)


# ── SQLite DB 파일 크기 메트릭 ───────────────────────────────────────────────
# Beat 태스크(db_health_task)가 60초마다 os.path.getsize()로 읽어 갱신한다.
# 어제(2026-05-14) 12GB 비대화 사고의 재발 방지용 — 5GB 경고 / 10GB 경보 기준.
# PG 전환 후에는 이 메트릭이 자연히 0으로 수렴한다.
SQLITE_DB_SIZE = Gauge(
    "sqlite_db_size_bytes",
    "SQLite database file size in bytes",
    multiprocess_mode="max",
)

# ── Celery 태스크 실행시간 / 대기시간 메트릭 ─────────────────────────────────
# C1: 태스크가 실제로 실행된 시간 (task_prerun → task_postrun).
# C2: 태스크가 큐에 들어간 시점부터 워커가 꺼낼 때까지 대기한 시간.
#
# 두 메트릭을 분리하는 이유:
#   - C1이 높으면 "태스크 로직 자체가 느린 것" (DB 락, 외부 API 지연 등)
#   - C2가 높으면 "worker가 태스크를 소화 못 하는 것" (worker 증설 필요)
#   - celery_queue_length가 짧아도 C1이 높으면 알람이 지연될 수 있다.
#
# 레이블:
#   task_name : 태스크 모듈 경로 (예: apps.alerts.tasks.fire_gas_alarm_task)
CELERY_TASK_DURATION = Histogram(
    "celery_task_duration_seconds",
    "Celery task execution time from task_prerun to task_postrun",
    ["task_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0],
)

CELERY_TASK_QUEUED = Histogram(
    "celery_task_queued_seconds",
    "Celery task wait time from enqueue to worker pickup",
    ["task_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0],
)

# ── AI 우선순위 mute 메트릭 ───────────────────────────────────────────────────
# Step 3 — AI 발화 시 같은 채널의 룰 알람을 60s 동안 mute 한다. 룰 fire 가 가드로
# skip 되는 횟수를 추적해 운영 중 "왜 룰이 안 떴나?" 디버깅 자료로 쓰고, AI 의 오탐
# 가능성을 시계열로 점검 (mute 빈도가 비정상적으로 높으면 AI 임계치 재학습 신호).
#
# 레이블:
#   device_id : PowerDevice.id (string). cardinality 우려 적음 (현재 64개 미만).
#   channel   : "1"~"16" — _INFERENCE_ENABLED_CHANNELS 확장 시 사용 채널만 증가.
#   level     : "warning" | "danger" — skip 된 룰 fire 의 위험 단계.
RULE_FIRE_SUPPRESSED_BY_AI_TOTAL = Counter(
    "rule_fire_suppressed_by_ai_total",
    "Rule alarm fire skipped because an AI alarm fired on the same channel recently",
    ["device_id", "channel", "level"],
)

# T4 D3 — STATIC_THRESHOLD_AT_FASTAPI=True 시 DRF 정적 fire skip 카운터.
# 활성화 모드의 동작 확인 + 시연 후 mismatch 분석 자료. 비활성화 모드에선 inc 0.
STATIC_FIRE_SUPPRESSED_BY_FASTAPI_TOTAL = Counter(
    "static_fire_suppressed_by_fastapi_total",
    "DRF static fire skipped because fastapi is the single decision-maker (T4)",
    ["device_id", "channel", "level"],
)

# T4 D3 — shadow_audit mismatch 카운터. DRF 정적 평가는 fire 해야 함이라 판단했는데
# fastapi 가 실제 알람 안 만든 케이스 누적. 1~2주 운영 후 0/낮음이면 활성화 안전.
STATIC_AUDIT_MISMATCH_TOTAL = Counter(
    "static_audit_mismatch_total",
    "Shadow audit: DRF would-fire but fastapi produced no AlarmRecord in window",
    ["device_id", "channel", "would_fire"],
)

# ── Celery 태스크 실패 / 재시도 메트릭 (P2 전) ───────────────────────────────
# task_postrun은 성공/실패 무관하게 호출되므로 실패 여부를 구분할 수 없다.
# task_failure / task_retry 시그널로 각각 카운트한다.
#
# 실패 카운터가 올라가면 알람 미발송 원인 추적 시작점이 된다.
# 재시도 카운터가 꾸준히 올라가면 FastAPI 불안정 또는 DB 락 신호.
#
# 레이블:
#   task_name : 태스크 모듈 경로 (예: apps.alerts.tasks.fire_gas_alarm_task)
CELERY_TASK_FAILED_TOTAL = Counter(
    "celery_task_failed_total",
    "Celery task failures (exception raised, not retried)",
    ["task_name"],
)

CELERY_TASK_RETRIED_TOTAL = Counter(
    "celery_task_retried_total",
    "Celery task retry count (re-enqueued after failure)",
    ["task_name"],
)
