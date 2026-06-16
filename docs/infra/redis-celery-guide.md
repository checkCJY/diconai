# Redis & Celery 인프라 가이드

> **한 줄 요약** — Redis 한 인스턴스가 5가지 역할(Celery broker / Django cache / WS 알람 큐 / dedup 상태 / AI mute 가드)을 모두 맡고, Celery는 13개 task + 4개 주기 Beat job 으로 알람·로그·유지보수를 비동기 처리한다.

작성일: 2026-05-23
대상: 백엔드/인프라 담당, 코드 미숙지 상태에서도 구조 파악 가능

---

## 0. TL;DR

| 질문 | 답 |
|---|---|
| Redis 어디서 돌고 있나? | docker-compose `redis:7-alpine` 단일 컨테이너 |
| Celery worker는? | 컨테이너 2개 — `celery-worker` (concurrency=2) + `celery-beat` |
| broker / result backend | 둘 다 `REDIS_URL` (`redis://redis:6379/0`) |
| Pub/Sub 쓰나? | **안 씀.** WS 알람 전달은 Redis **Stream** (XADD/replica별 XREAD, fan-out) |
| 알람 흐름 진입점 | `fastapi-server/routers/...` → DRF Celery task → fastapi `/internal/alarms/push/` → WS broadcast |
| dedup은 어디서? | 3개 계층 — DRF cache, fastapi fingerprint, AI mute 가드 (모두 Redis) |

---

## 1. 인프라 구성도

```
                ┌──────────────────────────────────────────────┐
                │             Redis (7-alpine)                 │
                │  ┌────────┐ ┌────────┐ ┌──────────────────┐  │
                │  │ broker │ │ cache  │ │ ws 알람 Stream  │  │
                │  │  list  │ │ keys   │ │ diconai:ws:alarms│  │
                │  └────────┘ └────────┘ └──────────────────┘  │
                └──┬────────────┬──────────────┬───────────────┘
                   │            │              │
        ┌──────────┴───┐  ┌─────┴────┐  ┌──────┴───────┐
        │ celery-worker│  │   drf    │  │   fastapi    │
        │ (-c 2)       │  │  (8000)  │  │   (8001)     │
        │ + celery-beat│  │ gunicorn │  │   uvicorn    │
        └──────────────┘  └──────────┘  └──────────────┘
                                │              │
                                │              │
                          ┌─────┴──────┐  ┌────┴────┐
                          │ PostgreSQL │  │ Browser │
                          │ (16-alpine)│  │  WS     │
                          └────────────┘  └─────────┘
```

**서비스별 책임**

| 서비스 | 책임 | 포트 | 비고 |
|---|---|---|---|
| `redis` | broker / cache / 큐 / state 키 | 6379 | appendonly 영속화 |
| `celery-worker` | task 실행 (알람·로그·유지보수) | — | concurrency=2 |
| `celery-beat` | 주기 task 스케줄러 | — | crontab + timedelta |
| `drf` | DB 영속화·관리자 페이지·인증·REST API | 8000 | gunicorn 1 worker × 4 threads |
| `fastapi` | 센서 수신·AI 추론·WebSocket broadcast | 8001 | uvicorn |
| `postgres` | 영속 DB | 5432 | PG 16 |

---

## 2. Redis 역할 5가지

### 2.1. Celery Broker + Result Backend

`drf-server/config/settings.py`

```python
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL        # 태스크 큐 (Redis list 기반)
CELERY_RESULT_BACKEND = REDIS_URL    # 태스크 실행 결과 저장
```

- task 발행 시 Redis list `celery` 에 LPUSH
- worker가 BRPOP으로 받아서 실행
- 결과는 `celery-task-meta-{task_id}` 키에 저장 (자동 만료)

### 2.2. Django RedisCache (애플리케이션 캐시)

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}
```

Django `cache.set/get/delete` 가 모두 이 backend로 향한다. **자동으로 `:1:` prefix 가 붙는다** (Django 캐시 버전 prefix).

**사용처 6곳**

| 모듈 | 키 prefix | TTL | 용도 |
|---|---|---|---|
| [alarm_dedupe.py](../../drf-server/apps/alerts/services/alarm_dedupe.py) | `alarm:state:*` / `alarm:power:state:*` | 60s | 알람 상태 전이 dedup |
| [gas_alarm.py](../../drf-server/apps/monitoring/services/gas_alarm.py) | `alarm:state:{sensor}:{gas}`, `alarm:task:{sensor}:{gas}` | 60s / 8s | 가스 dedup + WARNING task ID |
| [power_alarm.py](../../drf-server/apps/monitoring/services/power_alarm.py) | `alarm:power:state/task/risk:{...}` | 60s / 8s / 300s | 전력 dedup + 축별 위험도 |
| [threshold_service.py](../../drf-server/apps/facilities/services/threshold_service.py) | `threshold:{group}:{item}:{facility}` | 300s | 임계치 조회 캐시 |
| [policy_matcher.py](../../drf-server/apps/alerts/services/policy_matcher.py) | `alert_policies:{event_type}` | 300s | 알림 정책 매처 캐시 |
| [menu.py](../../drf-server/apps/dashboard/menu.py) | `dashboard:menu:{role}` | 300s | 사이드바 메뉴 트리 캐시 |

### 2.3. WS 알람 큐 (Raw Redis Stream, Django cache 우회)

[fastapi-server/websocket/services/alarm_queue.py](../../fastapi-server/websocket/services/alarm_queue.py)

> **2026-06 — LIST/BRPOP → Stream/XREAD 전환.** BRPOP은 "경쟁 소비"(한 알람을 한 소비자만
> pop)라 replica를 늘리면 알람이 누락된다. Stream + **replica별 독립 XREAD**(커서 보유)로
> 바꿔 모든 replica가 모든 알람을 받는 fan-out 구조로 만들었다. **Consumer Group은 미사용**
> — 그룹은 경쟁 분배라 fan-out이 안 된다.

```python
ALARM_QUEUE_KEY = "diconai:ws:alarms"   # ← Django cache prefix `:1:` 안 붙음
MAX_QUEUE_LEN = 10_000                  # XADD MAXLEN ~ 로 폭주 시 가장 오래된 알람 drop
```

| 연산 | 위치 | 의미 |
|---|---|---|
| `XADD diconai:ws:alarms MAXLEN ~ 10000 * data <json>` | [push_alarm()](../../fastapi-server/websocket/services/alarm_queue.py) | 알람 1건 적재 (트리밍 내장 — 별도 LTRIM 없음) |
| `XREAD BLOCK <ms> STREAMS diconai:ws:alarms <last_id>` | [alarm_flush_loop()](../../fastapi-server/websocket/routers/ws_router.py) | 커서(last_id) 이후 누적분을 배치로 읽음. 커서는 루프가 메모리 보유 |
| `XREVRANGE ... COUNT 1` | stream lag 계산 | 말단 ID ↔ 커서 시간차 (`ALARM_STREAM_LAG`) |
| `XLEN` | metrics export | `ALARM_QUEUE_LENGTH` Gauge |
| `TYPE`/`DEL` (startup 1회) | reset_stream_if_wrongtype() | 잔존 LIST만 정리 (WRONGTYPE 방지) |

**왜 Pub/Sub가 아니라 Stream인가**: 알람은 손실 금지 — Pub/Sub의 "구독자 없으면 즉시 손실"
특성과 충돌. Stream은 fastapi 일시 다운/클라 부재 시에도 적체 → 복귀 후 커서 이후 누적분을
한 번에 전달. (List도 적체는 됐지만 BRPOP=경쟁 소비라 다중 replica fan-out 불가였다.)

### 2.4. Dedup/State 키 (Raw)

알람 큐 진입 직전에 한 번 더 fingerprint 기반 dedup이 걸린다. Celery retry로 인한 동일 알람 중복 push 방지.

| 키 | 연산 | TTL | 용도 |
|---|---|---|---|
| `alarm:push:dedup:{fingerprint}` | `SET NX EX` | 60s | 첫 도착자만 XADD 통과 |

fingerprint 형식:
- 룰 알람: `event:{event_id}:{risk_level}`
- AI anomaly: `ai:{alarm_type}:{device}:{channel}:{level}`
- 정상화: `clear:{alarm_type}:{source_label}`
- T4 cover: `cover:{source}:{label}:{level}`

### 2.5. AI Mute 가드 (Cross-server Raw)

fastapi 가 AI 알람을 발화하면 같은 채널의 룰 알람을 일정 시간(60s) 억제. **fastapi와 drf 양쪽이 Django cache 우회하고 raw redis로 같은 키를 set/exists.**

| 키 | 누가 SET | 누가 READ | TTL |
|---|---|---|---|
| `ai_fired:{device_id}:{channel}:{level}` | [fastapi/services/ai_mute.py](../../fastapi-server/services/ai_mute.py) `mark_ai_recent()` | [drf/alarm_dedupe.py](../../drf-server/apps/alerts/services/alarm_dedupe.py) `is_ai_mute_active()` | 60s |
| `ai_state:{device}:{channel}:{data_type}` | fastapi (5 state 마킹) | fastapi 자기 자신 | 5분 |

Raw redis로 가는 이유 — Django RedisCache의 pickle 직렬화 + `:1:` prefix가 fastapi의 redis-py 와 호환되지 않기 때문.

---

## 3. Redis 키 인벤토리 (한눈에)

| 키 패턴 | 데이터 타입 | TTL | 용도 | 정의 위치 |
|---|---|---|---|---|
| `diconai:ws:alarms` | Stream | — | WS 알람 큐 (XADD/XREAD, fan-out) | fastapi alarm_queue.py |
| `alarm:push:dedup:{fp}` | String (NX) | 60s | 알람 push 중복 차단 | fastapi alarm_queue.py |
| `:1:alarm:state:{sensor}:{gas}` | String | 60s | 가스 알람 상태 (dedup) | drf gas_alarm.py |
| `:1:alarm:task:{sensor}:{gas}` | String | 8s | 가스 WARNING celery task ID | drf gas_alarm.py |
| `:1:alarm:power:state:{dev}:{ch}` | String | 60s | 전력 알람 상태 | drf power_alarm.py |
| `:1:alarm:power:task:{dev}:{ch}` | String | 8s | 전력 WARNING celery task ID | drf power_alarm.py |
| `:1:alarm:power:risk:{dev}:{ch}:{axis}` | String | 300s | 축(W·A·V)별 마지막 위험도 | drf power_alarm.py |
| `ai_fired:{dev}:{ch}:{level}` | String | 60s | AI mute 가드 | fastapi ai_mute.py |
| `ai_state:{dev}:{ch}:{data_type}` | String | 5분 | AI 5-state 마킹 | fastapi ai_mute.py |
| `:1:threshold:{group}:{item}:{facility}` | Pickle | 300s | 임계치 캐시 | drf threshold_service.py |
| `:1:alert_policies:{event_type}` | Pickle | 300s | 알림 정책 캐시 | drf policy_matcher.py |
| `:1:dashboard:menu:{role}` | Pickle | 300s | 사이드바 메뉴 캐시 | drf menu.py |
| `celery-task-meta-{task_id}` | String | (자동) | Celery task 실행 결과 | Celery 내부 |
| `celery` (list) | List | — | Celery broker 큐 | Celery 내부 |

**디버깅 명령**

```bash
# 전체 키 카테고리 확인 (운영에선 SCAN 권장)
docker compose exec redis redis-cli --scan --pattern 'diconai:*'
docker compose exec redis redis-cli --scan --pattern 'ai_fired:*'

# 알람 큐(스트림) 길이
docker compose exec redis redis-cli XLEN diconai:ws:alarms

# 특정 dedup 키 TTL 확인
docker compose exec redis redis-cli TTL "ai_fired:1:5:warning"
```

---

## 4. Celery 구성

### 4.1. Worker / Beat 컨테이너

[docker-compose.yml](../../docker-compose.yml)

| 컨테이너 | 명령 | concurrency | 환경 |
|---|---|---|---|
| `celery-worker` | `celery -A config worker -l info --concurrency=2` | 2 | drf 이미지 재사용 |
| `celery-beat` | `celery -A config beat -l info` | 1 | drf 이미지 재사용 |

**Prometheus multiprocess 모드**: drf/celery 컨테이너가 같은 `/app/prometheus_multiproc/` 볼륨을 공유하지만 서브디렉토리 분리 (`drf/` vs `celery/`). 한쪽 재시작이 다른 쪽 메트릭 파일을 지우지 않도록 격리. drf의 `/metrics` 엔드포인트가 두 디렉토리를 합산.

### 4.2. Task 인벤토리 (13개)

[drf-server/apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py)

| Task | 트리거 | retry | 대기 | 용도 |
|---|---|---|---|---|
| `fire_danger_alarm_task` | 가스 DANGER 감지 (gas_alarm.py) | 3 | 즉시 | 가스 DANGER AlarmRecord + WS push |
| `fire_warning_alarm_task` | 가스 WARNING 감지 | 3 | countdown=3s | WARNING 3초 지속 후 발화 |
| `fire_clear_notification_task` | 가스 NORMAL 복귀 | 3 | 즉시 | 정상화 알림 |
| `fire_power_danger_task` | 전력 DANGER (power_alarm.py) | 3 | 즉시 | 전력 DANGER |
| `fire_power_warning_task` | 전력 WARNING | 3 | countdown=3s | 전력 WARNING 3초 |
| `fire_power_clear_task` | 전력 NORMAL 복귀 | 3 | 즉시 | 전력 정상화 |
| `fire_geofence_alarm_task` | 작업자 지오펜스 진입 | 3 | 즉시 | 지오펜스 알람 |

[drf-server/apps/operations/tasks/](../../drf-server/apps/operations/tasks/)

| Task | 트리거 | 용도 |
|---|---|---|
| `integration_log_create_task` | _push_to_ws 호출 후 | DRF↔fastapi 통합 로그 |
| `applog_create_task` | DBHandler (logging) | 애플리케이션 로그 비동기 INSERT |
| `run_data_retention` | Beat: 매일 09:30 | Raw 데이터 보존 정책 적용 |
| `record_celery_queue_length` | Beat: 30초마다 | 큐 길이 → Prometheus Gauge |
| `record_db_health` | Beat: 60초마다 | DB 파일 크기/카운트 → Gauge |
| `clear_sessions` | Beat: 일요일 03시 | 만료 Django 세션 정리 |

### 4.3. Beat 스케줄

[drf-server/config/settings.py](../../drf-server/config/settings.py) `CELERY_BEAT_SCHEDULE`

```python
CELERY_BEAT_SCHEDULE = {
    "data_retention_daily":          crontab(hour=9, minute=30),     # 09:30 KST
    "celery_queue_length_metrics":   timedelta(seconds=30),          # 30초마다
    "db_health_metrics":             timedelta(seconds=60),          # 60초마다
    "clear_expired_sessions":        crontab(day_of_week=0, hour=3), # 일요일 03시
}
```

**참고**: 데이터 보존이 09:30인 이유 — 03시는 호스트 WSL2/Docker가 꺼져 있어 미발사 사례가 있었음(2026-05-14).

### 4.4. Celery Signal 메트릭

[drf-server/config/celery.py](../../drf-server/config/celery.py) 가 5개 signal에 메트릭 핸들러를 등록한다.

| Signal | 메트릭 | 용도 |
|---|---|---|
| `before_task_publish` | (헤더 주입) | enqueued_at 시각 기록 |
| `task_prerun` | `CELERY_TASK_QUEUED` (Histogram) | 큐 대기 시간 |
| `task_postrun` | `CELERY_TASK_DURATION` (Histogram) | 실행 시간 |
| `task_failure` | `CELERY_TASK_FAILED_TOTAL` (Counter) | 최종 실패 카운트 |
| `task_retry` | `CELERY_TASK_RETRIED_TOTAL` (Counter) | 재시도 카운트 |

---

## 5. 핵심 데이터 흐름

### 5.1. 알람 흐름 (가스 기준, 전력도 동일 패턴)

```
[1] IoT 디바이스
    └─ POST /api/sensors/gas → fastapi
                                  ↓
[2] fastapi gas_service.process_gas_data()
    ├─ AI 추론 (sklearn IF) → ai_mute.mark_ai_recent (Redis SET)
    └─ HTTP POST → drf POST /api/monitoring/gas/
                                  ↓
[3] drf GasDataBulkIngestSerializer.create()
    └─ trigger_gas_alarms(objs)
                                  ↓
[4] gas_alarm.trigger_gas_alarms()
    ├─ alarm_dedupe.try_transition()  → Redis cache (alarm:state:*)
    │    └─ False면 skip (같은 상태 재진입)
    │    └─ True면 ↓
    ├─ DANGER → fire_danger_alarm_task.delay()
    └─ WARNING → fire_warning_alarm_task.apply_async(countdown=3)
                                  ↓
[5] Redis broker (list "celery")
                                  ↓
[6] celery-worker가 BRPOP
    └─ fire_danger_alarm_task 실행
        ├─ create_alarm_and_event() → PostgreSQL (AlarmRecord/Event)
        └─ _push_to_ws() → HTTP POST → fastapi /internal/alarms/push/
                                  ↓
[7] fastapi push_alarm_handler()
    └─ alarm_queue.push_alarm()
        ├─ SET NX EX "alarm:push:dedup:{fp}" → 첫 도착자만 통과
        └─ XADD "diconai:ws:alarms" MAXLEN ~ 10000 (트리밍 내장)
                                  ↓
[8] alarm_flush_loop (백그라운드, replica별 독립 커서)
    └─ XREAD BLOCK "diconai:ws:alarms" <last_id> (커서 이후 배치)
        └─ sensor_clients 전체에 WebSocket broadcast (fan-out)
                                  ↓
[9] 브라우저 토스트 표시
```

### 5.2. AI 추론 → mute 마킹 → 룰 가드

```
fastapi gas_service / power_service
   ↓
process_anomaly_inference()
   ├─ sklearn Isolation Forest 추론
   ├─ 임계 위험도 발화 시:
   │    ├─ ai_mute.mark_ai_recent(device_id, channel, level)
   │    │    └─ Redis SET "ai_fired:{dev}:{ch}:{level}" EX 60
   │    └─ anomaly_alarm.push_anomaly_alarm() → XADD "diconai:ws:alarms"
   ↓ (별도 흐름)
drf power_alarm.trigger_power_alarms()
   └─ alarm_dedupe.is_ai_mute_active(device_iot_id, channel, "warning")
        └─ Redis EXISTS "ai_fired:{dev}:{ch}:warning"
            └─ True면 → RULE_FIRE_SUPPRESSED_BY_AI_TOTAL.inc() + skip
            └─ False면 → 정상 fire_power_*_task.delay()
```

**핵심 포인트**: fastapi(SET)와 drf(EXISTS)가 **같은 raw key**를 직접 조작. Django RedisCache 우회는 prefix 충돌 회피 때문.

### 5.3. Dedup 3계층

같은 알람이 중복 발화되지 않도록 3계층 가드가 있다.

| 계층 | 위치 | 키 | 무엇을 막나 |
|---|---|---|---|
| ① 상태 전이 | drf alarm_dedupe.try_transition | `:1:alarm:state:*` | 같은 상태 재진입 (NORMAL→NORMAL 등) |
| ② AI mute | drf alarm_dedupe.is_ai_mute_active | `ai_fired:*` | AI 발화 직후 60s 룰 알람 |
| ③ Push fingerprint | fastapi alarm_queue.push_alarm | `alarm:push:dedup:*` | Celery retry로 인한 중복 XADD |

각 계층은 직교 — ①이 통과한 알람도 ③에서 fingerprint 일치 시 차단될 수 있다.

---

## 6. 운영 시 알아야 할 것

### 6.1. 환경변수

| 변수 | 기본값 | 어디서 쓰나 |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | broker / cache / raw |
| `FASTAPI_INTERNAL_URL` | `http://127.0.0.1:8001` | DRF → fastapi `/internal/alarms/push/` |
| `INTERNAL_SERVICE_TOKEN` | (빈 값) | drf↔fastapi Bearer 인증 |
| `STATIC_THRESHOLD_AT_FASTAPI` | `False` | T4 D3 — fastapi 단일 결정자 모드 |

### 6.2. 핵심 Prometheus 메트릭

| 메트릭 | 의미 | 정상 범위 |
|---|---|---|
| `ALARM_QUEUE_LENGTH` | `XLEN diconai:ws:alarms` | < 100 |
| `ALARM_STREAM_LAG` | 스트림 말단↔replica 커서 시간차(초) | 평상시 ≈0 |
| `ALARM_WS_PUSH_FAILED_TOTAL` | DRF→fastapi push 실패 | 0 증가 |
| `REDIS_COMMAND_DURATION{cmd}` | `xadd` 명령 지연 (`xread`는 BLOCK 대기 섞여 미측정) | p95 < 10ms |
| `CELERY_TASK_QUEUED{task_name}` | task 큐 대기 시간 | p95 < 100ms |
| `CELERY_TASK_DURATION{task_name}` | task 실행 시간 | task별 상이 |
| `CELERY_TASK_FAILED_TOTAL` | 최종 실패 카운트 | 0 |
| `CELERY_TASK_RETRIED_TOTAL` | 재시도 카운트 | 낮을수록 좋음 |
| `RULE_FIRE_SUPPRESSED_BY_AI_TOTAL` | AI mute로 차단된 룰 알람 | 점진적 증가 정상 |

### 6.3. 디버깅 체크리스트

**증상: 알람이 브라우저에 안 뜬다**
1. `redis-cli XLEN diconai:ws:alarms` — 스트림에 쌓여 있는지? (+ `ALARM_STREAM_LAG`로 뒤처지는 replica 식별)
2. `redis-cli --scan --pattern 'alarm:push:dedup:*'` — fingerprint 키가 너무 많이 잡혀 있다면 retry 폭주
3. `ALARM_WS_PUSH_FAILED_TOTAL` 증가? — DRF→fastapi HTTP POST 실패
4. fastapi `alarm_flush_loop` 살아 있는지? (uvicorn 로그)

**증상: Celery task가 안 돈다**
1. `celery -A config inspect active` — worker가 살아 있는지
2. `redis-cli LLEN celery` — broker 큐에 쌓여 있는지
3. `CELERY_TASK_RETRIED_TOTAL` 급증 — task 자체 실패 패턴

**증상: AI 알람과 룰 알람이 동시에 뜬다 (mute 가드 미동작)**
1. `redis-cli EXISTS "ai_fired:{device}:{channel}:warning"` — 키가 진짜 있는지
2. fastapi `mark_ai_recent` 가 실제로 호출됐는지 (로그)
3. drf의 `is_ai_mute_active` 가 같은 키 패턴으로 read하는지 (device_iot_id 사용 필수)

### 6.4. Redis 장애 시 영향 범위

| Redis 다운 시 | 영향 | 회피 |
|---|---|---|
| Celery broker | 신규 task 발행 불가 | drf가 task.delay 시 graceful fallback (silent fail) |
| Django cache | 모든 cache.get → None → DB hit | 자동 fallback (성능만 저하) |
| WS 알람 큐 | XADD 실패 → fastapi `/internal/alarms/push/` 503 | DRF Celery가 max_retries=3로 재시도 |
| AI mute 가드 | mark_ai_recent silent fail / is_ai_mute_active fail-open | AI/룰 중복 발화 가능 (안전 측 fallback) |

**원칙**: Redis 장애가 알람 흐름을 멈추지 않도록 모든 raw redis 호출은 silent fail 또는 fail-open.

---

## 7. 확장 시점 시그널 (참고)

현재는 단일 fastapi + 단일 drf 인스턴스 구조. 다음 신호가 보이면 Phase 2 진입 검토.

| 시그널 | 임계값 | 조치 |
|---|---|---|
| 동시 WebSocket 연결 | > 500 지속 | uvicorn `--workers N` 수직 확장 |
| fastapi CPU | > 70% 지속 | 워커 증설 → 안 되면 다중 인스턴스 |
| `ALARM_QUEUE_LENGTH` | > 100 지속 | flush 루프 소비 지연 — `ALARM_STREAM_LAG`로 어느 replica가 뒤처지는지 확인 |
| broadcast latency p95 | > 500ms | fastapi replica 증설 (전송 계층은 이미 Stream+replica별 XREAD로 fan-out 준비 완료 — replica≥2 활성화만 남음. **Consumer Group 아님** — 그룹은 경쟁 분배라 fan-out 불가) |
| `CELERY_TASK_QUEUED` p95 | > 1s | worker concurrency ↑ 또는 큐 분리 |

**Phase 2 마이그레이션 시 변경 예상 지점**:
- ~~WS 알람 큐 `List` → `Streams`~~ **(2026-06 완료)** — Stream + **replica별 XREAD**로 전송 계층 fan-out 준비 완료. 남은 건 replica≥2 활성화 + replica 식별 라벨. (Consumer Group은 경쟁 분배라 미채택)
- 정책 변경 / 캐시 invalidation → 진짜 Redis `Pub/Sub` 도입 (모든 인스턴스 동시 알림)
- AI 추론 → 별도 Celery 큐 (현재는 fastapi 인라인)

---

## 8. 관련 문서

- [Docker 환경 셋업](docker_setup.md)
- [알람 팝업 장애 트러블슈팅](troubleshooting_alarm_popup_docker.md)
- 코드 진입점: [alerts/tasks.py](../../drf-server/apps/alerts/tasks.py), [alarm_queue.py](../../fastapi-server/websocket/services/alarm_queue.py)
