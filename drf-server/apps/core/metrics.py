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
