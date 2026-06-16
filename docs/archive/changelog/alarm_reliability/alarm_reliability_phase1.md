# 알람 신뢰성 개선 Phase 1 — 변경 요약

> **요약 한 줄**: 알람이 "안 뜨거나/늦거나/중복으로 뜨거나/DB locked 에러가 나던" 4가지 증상을 5단계 백엔드 변경으로 한 번에 해소.

**브랜치**: `feature/alarm_refactory` · **커밋**: 5개 (C1~C5) · **머지 PR 단위**: 단일 PR · **상세 plan**: [skill/plan/alarm-reliability-phase1.md](../../../../skill/plan/alarm-reliability-phase1.md) (gitignore 영역)

---

## 왜 이 작업을 했나

### 사용자가 보고한 증상

| 증상 | 빈도 | 추정 원인 |
|---|---|---|
| 알람이 안 뜸 (silent drop) | 자주 | WS 신호 race / 큐 cap / push 실패 |
| 알람이 지연됨 | 자주 | broadcast 5초 주기 + 신호 손실 |
| 같은 위험에 알람 중복 | 자주 | DB 동시 쓰기 race / 캐시 비원자 dedupe |
| `database is locked` 에러 | 가끔 | SQLite 기본 journal_mode=DELETE (단일 writer) |

### 코드 검토에서 확인한 결함 8가지

| # | 문제 | 위치 | 영향 |
|---|---|---|---|
| 1 | SQLite WAL 미설정 | `config/settings.py` | 동시 쓰기 lock |
| 2 | `cache.get → fire_task.delay → cache.set` 비원자 | `gas_alarm.py` / `power_alarm.py` | 중복 알람 fire |
| 3 | `bulk_create(ignore_conflicts=True)` 후 원본 `objs`로 알람 트리거 | `serializers/power_data.py` | DB엔 없는 행에 알람 발화 |
| 4 | `active_alarms`(메모리 list) FastAPI 재시작 시 휘발 | `websocket/state.py` | 미전달 알람 영구 손실 |
| 5 | `alarm_signal`(asyncio.Event) set/clear race | `websocket/routers/ws_router.py` | 알람 silent drop |
| 6 | `is_new_event` 필터로 정상화 알림 silent drop | 같음 | 회복 알림 누락 |
| 7 | `active_alarms[:5]` cap | `websocket/services/broadcast.py` | 폭주 시 다음 tick까지 대기 |
| 8 | Celery → FastAPI push `timeout=3.0` + silent fail | `apps/alerts/tasks.py:_push_to_ws` | DB엔 있고 브라우저엔 없음 |

### 인프라 제약

- **SQLite 유지** (PostgreSQL 이관은 추후 — 본 Phase는 SQLite로도 안정성 확보)
- **Redis는 이미 도커 컴포즈에서 가동 중** (`diconai-redis-1`, redis:7-alpine) — Celery broker + Django 캐시로 사용 중

---

## 단계별 변경 (C1~C5)

각 단계는 단독 커밋이라 문제 발생 시 단계 단위 롤백 가능.

### C1 — SQLite WAL 모드 활성화 ([7efb9cd](#))

**무엇**
- 신규 [drf-server/apps/core/sqlite_pragmas.py](../../../../drf-server/apps/core/sqlite_pragmas.py) — Django `connection_created` signal에 receiver 등록. 매 connection 생성 시 PRAGMA 4종 적용:
  - `journal_mode=WAL` — 동시 reader / single writer 허용
  - `busy_timeout=5000` — lock 충돌 시 최대 5초 재시도
  - `synchronous=NORMAL` — WAL과 짝, fsync 부담 감소
  - `foreign_keys=ON` — SQLite 기본 OFF인 FK 강제 (Django ORM 의존)
- 수정 [drf-server/apps/core/apps.py](../../../../drf-server/apps/core/apps.py) — `CoreConfig.ready()`에서 위 모듈 import

**왜**
- 기존 journal_mode=DELETE는 한 번에 1 writer만 허용 → 다중 Celery 워커 + 동시 센서 수신 시 `database is locked` 자주 발생
- WAL은 reader와 writer를 분리 trace로 처리 → 동시성 대폭 향상
- `connection.vendor != "sqlite"` 가드로 PostgreSQL 이관 시 자동 noop — 향후 이관에 부담 없음

**검증**
```bash
# 동시 INSERT 200건 (40 thread) — locked 0건 확인
docker exec diconai-drf-1 python -c "..." # plan §검증 참조
# 결과: 성공 200/200, locked 0, 0.15초
```

---

### C2 — 알람 dedupe 원자화 ([314c1c0](#))

**무엇**
- 신규 [drf-server/apps/alerts/services/alarm_dedupe.py](../../../../drf-server/apps/alerts/services/alarm_dedupe.py)
  - Redis Lua로 `GET → CMP → SET`을 단일 원자 명령으로 실행
  - `cache.make_key()` + `pickle.dumps()`로 Django RedisCache와 동일 키 공간/직렬화 사용 (기존 `cache.get`/`cache.add` 코드와 호환)
  - 3개 헬퍼: `try_transition`, `get_state`, `clear_state`
- 수정 [gas_alarm.py](../../../../drf-server/apps/monitoring/services/gas_alarm.py), [power_alarm.py](../../../../drf-server/apps/monitoring/services/power_alarm.py)
  - DANGER: `if try_transition(state_key, "danger"): fire_*_task.delay(...)` — fire와 상태 갱신이 1 연산
  - WARNING: `cache.add(task_key, ..., ttl)` SETNX 가드로 첫 도착자만 타이머 시작
  - NORMAL: `clear_state(state_key)`로 명시적 키 삭제

**왜**
- 기존 흐름: `prev = cache.get(state_key); if prev != "danger": fire(); cache.set(state_key, "danger")` — 3 step
- 동시 100건이 도착하면 모두 step 1에서 `"normal"`을 받고 step 2 통과 → fire 100번 발생 가능
- Redis Lua는 단일 명령으로 GET-CMP-SET 모두 실행 → 정확히 1건만 천이 성공, 나머지는 skip

**향후 호환성**
- 전력 §2-3 (W·A·V 확장), IF §2-3 (combined_risk 결합) 모두 `try_transition` 호출 시그니처를 그대로 유지. 인자만 바뀜.

**검증**
```bash
# 동시 100건 try_transition('danger') 호출 → 정확히 True 1회
# 결과: True 1 / False 99 — race-safe 확인
```

---

### C3 — PowerData bulk_create 정합성 ([06f7e91](#))

**무엇**
- 수정 [drf-server/apps/monitoring/serializers/power_data.py](../../../../drf-server/apps/monitoring/serializers/power_data.py)
  - `bulk_create(objs, ignore_conflicts=True)` 직후 unique 조건으로 `filter()` 재조회
  - `(power_device, channel, data_type, measured_at)` 복합 UNIQUE 기반
  - 실제 저장된 행(`saved`)만 `trigger_power_alarms`에 전달

**왜**
- `ignore_conflicts=True` 옵션은 중복 행 INSERT를 silent skip하지만, 입력 `objs` 리스트는 skip 여부와 무관하게 그대로 남음
- 기존 코드는 `trigger_power_alarms(objs, device)`로 미저장 행에도 알람 발화 → 운영자가 보기엔 알람이 떴는데 DB엔 측정값 없음 (정합성 깨짐)
- DB 엔진 무관 (ORM 표준 API) — PostgreSQL 이관 후에도 동일 동작

**검증**
- 동일 payload 2회 호출 (전체 conflict): saved=2, DB 행 수 2
- 부분 충돌 (2개 중 1개 신규): saved=2, DB 총 행 수 3
- 모든 시나리오에서 saved 리스트와 DB 실제 행 일치

---

### C4 — `active_alarms` → Redis LIST 전환 ([57e8391](#))

가장 큰 변경. 9개 파일 영향.

**무엇**
- 신규 [fastapi-server/core/redis_client.py](../../../../fastapi-server/core/redis_client.py) — `redis.asyncio` 싱글톤 클라이언트 (`get_redis()`, `close_redis()`)
- 신규 [fastapi-server/websocket/services/alarm_queue.py](../../../../fastapi-server/websocket/services/alarm_queue.py) — Redis LIST 추상화
  - `push_alarm(payload)` — `LPUSH diconai:ws:alarms` + `LTRIM 0 9999` (10k건 cap)
  - `pop_alarm_blocking(timeout=0)` — `BRPOP` 무한 대기 + ConnectionError 안전 처리
  - `queue_len()` — 메트릭/모니터링용
- 수정 [websocket/state.py](../../../../fastapi-server/websocket/state.py) — `active_alarms`, `alarm_signal`, `import asyncio` 삭제
- 수정 [internal/routers/alarm_router.py](../../../../fastapi-server/internal/routers/alarm_router.py) — `list.append + signal.set()` → `await push_alarm()` (LPUSH). Redis 장애 시 503 응답으로 Celery retry 유도. 핸들러 함수명 `push_alarm` → `push_alarm_handler` (헬퍼와 충돌 회피)
- 수정 [websocket/routers/ws_router.py](../../../../fastapi-server/websocket/routers/ws_router.py) `alarm_flush_loop` — `asyncio.Event.wait/clear` 패턴 → `pop_alarm_blocking()` (BRPOP) 패턴으로 재작성. `is_new_event` 필터 제거
- 수정 [websocket/services/broadcast.py](../../../../fastapi-server/websocket/services/broadcast.py) — `"alarms": list(active_alarms)[:5]` 슬라이스 제거. `"alarms": []` 고정 (주기 broadcast는 더 이상 알람 전달 책임 없음, `alarm_flush_loop`이 단독 담당)
- 수정 [app.py](../../../../fastapi-server/app.py) lifespan finally — `await close_redis()` 추가
- 의존성 [requirements.txt](../../../../fastapi-server/requirements.txt) — `redis==5.2.1` 추가
- 컴포즈 [docker-compose.yml](../../../../docker-compose.yml) — fastapi 서비스에 `REDIS_URL=redis://redis:6379/0` + `depends_on: redis: condition: service_healthy`

**왜**
3가지 결함을 한 번에 해결:
1. **재시작 휘발** — 기존 `active_alarms: list[dict] = []`는 FastAPI 프로세스 메모리 → 재시작 시 미전달 알람 영구 손실. Redis LIST는 별도 컨테이너에 영속.
2. **신호 race** — `asyncio.Event.set/clear` 사이에 도착한 알람이 신호 손실로 silent drop 가능. BRPOP은 큐에 원소가 들어오는 순간 깨어나며 pop과 소비가 1 연산.
3. **5개 cap** — `list(active_alarms)[:5] + del active_alarms[:5]`로 한 tick에 5건만 처리. 폭주 시 잔여는 다음 tick(최대 5초) 대기. Redis LIST는 cap 없이 순서대로 소비.

**WS 페이로드 호환 모드**
- 프론트 코드 무수정을 위해 기존 `{"alarms": [payload], ...}` shape 유지. `alarm_flush_loop`이 단건 pop 후 alarms 배열에 wrap해서 전송.
- 향후 Phase 2(UI)에서 `{type: "alarm", alarm: {...}}` 명시적 분리 검토.

**검증** (docker compose 실 환경)
- 인증 토큰 포함 `/internal/alarms/push/` POST → 200 OK, 큐 즉시 소비
- Redis 직접 LPUSH 2건 → 1초 후 큐 0 (BRPOP 정상)
- **영속성**: fastapi stop → LPUSH 2건 → 큐 길이 2 잔존 → fastapi start → 5초 내 큐 0 (재시작 후 잔여 알람 자동 소비)

---

### C5 — `_push_to_ws` 신뢰성 보강 ([5e80144](#))

**무엇**
- 수정 [drf-server/apps/alerts/tasks.py](../../../../drf-server/apps/alerts/tasks.py) `_push_to_ws`
  - timeout `3.0 → 10.0`초
  - HTTP 5xx 또는 `httpx.RequestError`/`HTTPStatusError` 시 `RuntimeError` raise
  - 4xx(페이로드 검증 실패)는 retry 의미 없어 raise 안 함
  - `raise_on_failure` 인자 추가 (기본 True)
- `fire_clear_notification_task` / `fire_power_clear_task`만 `raise_on_failure=False`로 호출 — 정상화 알림 손실 허용

**왜**
- 기존: timeout 3초 + 실패 silent fail + IntegrationLog `result=failure`만 기록
  - 도커 네트워크 RTT/콜드 스타트 마진 부족 (3초 자주 초과)
  - 실패해도 호출자(`fire_*_task`)는 정상 종료 → 알람 영구 누락
- 신규: 5xx/네트워크 오류 → RuntimeError raise → 호출자의 `except Exception as exc: raise self.retry(exc=exc)`가 흡수 → Celery `max_retries=3, default_retry_delay=5`로 자동 retry

**중복 발송 트레이드오프**
- DB는 이미 commit + WS push만 실패한 케이스에서 retry 시 동일 페이로드 2회 전송 가능
- Phase 1에선 허용 — 현재의 silent drop이 더 큰 문제
- 완전한 idempotency는 IF §2-3-a에서 `event_id` 기반 dedupe로 보강 예정 ([skill/plan/if-integration-guide.md](../../../../skill/plan/if-integration-guide.md) §2-3-a)

**검증** (3 시나리오)
1. FastAPI 살아있음 + 정상 push → 예외 없음 (200 OK)
2. FastAPI 다운 + `raise_on_failure=True` → `RuntimeError raise` (호출자 retry 흡수)
3. FastAPI 다운 + `raise_on_failure=False` (clear) → 예외 없이 손실 허용

---

## 누적 효과 (Phase 1 완료 시점)

| 증상 | Phase 1 이전 | Phase 1 이후 |
|---|---|---|
| `database is locked` | 가끔 발생 | 동시 200건 INSERT에서 0건 (C1) |
| 동시 동일 위험에 알람 중복 fire | 발생 가능 | 정확히 1회만 fire (C2) |
| DB엔 없는 행에 알람 발화 | bulk_create 시 발생 | saved 행만 trigger (C3) |
| FastAPI 재시작 시 알람 휘발 | 큐 메모리 → 손실 | Redis LIST → 자동 복구 (C4) |
| WS 신호 race로 silent drop | 발생 가능 | BRPOP 1연산 (C4) |
| 5개 cap으로 폭주 시 지연 | 다음 broadcast tick 대기 | 큐 순서대로 즉시 소비 (C4) |
| FastAPI push 일시 장애 시 누락 | silent fail | Celery retry 자동 복구 (C5) |

---

## 머지 후 운영 관찰 가이드

### 1주간 다음 지표 모니터링

**SQLite locked 에러 빈도** (C1 효과)
```bash
docker compose logs --since 1h drf 2>&1 | grep -ciE "database is locked|OperationalError.*locked"
# 기대: 0건
```

**알람 푸시 성공률** (C5 효과)
```python
# Django shell
from apps.operations.models.integration_log import IntegrationLog
from django.db.models import Count
IntegrationLog.objects.filter(target_system="DRF→FastAPI").values("result").annotate(n=Count("id"))
# 기대: success / failure 비율 ≥ 99%
```

**Redis 알람 큐 길이** (C4 효과)
```bash
docker exec diconai-redis-1 redis-cli LLEN diconai:ws:alarms
# 기대: 거의 항상 0 (BRPOP 즉시 소비). 1 이상이 자주 보이면 alarm_flush_loop이 죽었거나 sensor_clients=[] 지속 의심
```

**Celery retry 발생 빈도** (C5 효과 확인)
```bash
docker compose logs --since 1h celery-worker 2>&1 | grep -ciE "Retry in 5"
# 기대: 0건. 1건 이상 보이면 FastAPI 일시 장애 발생 — Phase 1이 자동 복구한 흔적
```

### 회귀 의심 신호

- WS 메시지 JSON 구조 변경으로 인한 프론트 콘솔 에러 → 호환 모드라 0건 기대. 발생 시 즉시 보고
- Redis 컨테이너 다운 시 영향: DRF는 Celery broker로도 Redis 의존 — Redis 다운 시 알람 푸시 + Celery task 자체 모두 영향. Phase 1과 무관한 기존 의존성
- `database is locked`가 여전히 보이면: WAL 활성화 확인
  ```bash
  docker exec diconai-drf-1 sqlite3 /app/db.sqlite3 "PRAGMA journal_mode;"
  # 기대: wal
  ```

---

## 다음 단계 (Phase 1 머지 후)

[skill/plan/alarm-reliability-phase1.md](../../../../skill/plan/alarm-reliability-phase1.md) "추천 진행 순서" ②~⑦ 참조.

```
①  Phase 1 (완료)
       ↓
②  가스 §1 + 전력 §1 (정격 필드 + Threshold 시드)   [병렬]
③  전력 §2 (W·A·V 평가 확장)
④  가스 §3 + 전력 §3 (더미 보강 + 라벨링)            [병렬]
⑤  IF §1 (apps/ml/ 신설)
⑥  IF §2 (알람 결합 매트릭스)
⑦  IF §3 + §5 (지속시간 + ARIMA + Change Point)
```

- Phase 2 (UI/UX): 백엔드와 독립이라 ②와 병렬 가능. `LevelMapper` 전역화, 모바일 반응형, 알람 팝업 가시성 등.
- Phase 1 코드는 PostgreSQL 이관 시 자동으로 호환 — `sqlite_pragmas.py`만 `vendor != "sqlite"` 가드로 noop, 나머지는 DB 무관.

---

## 코드 참조 일람

| 단계 | 파일 | 변경 |
|---|---|---|
| C1 | [drf-server/apps/core/sqlite_pragmas.py](../../../../drf-server/apps/core/sqlite_pragmas.py) | 신규 |
| C1 | [drf-server/apps/core/apps.py](../../../../drf-server/apps/core/apps.py) | 수정 |
| C2 | [drf-server/apps/alerts/services/alarm_dedupe.py](../../../../drf-server/apps/alerts/services/alarm_dedupe.py) | 신규 |
| C2 | [drf-server/apps/monitoring/services/gas_alarm.py](../../../../drf-server/apps/monitoring/services/gas_alarm.py) | 수정 |
| C2 | [drf-server/apps/monitoring/services/power_alarm.py](../../../../drf-server/apps/monitoring/services/power_alarm.py) | 수정 |
| C3 | [drf-server/apps/monitoring/serializers/power_data.py](../../../../drf-server/apps/monitoring/serializers/power_data.py) | 수정 |
| C4 | [fastapi-server/core/redis_client.py](../../../../fastapi-server/core/redis_client.py) | 신규 |
| C4 | [fastapi-server/websocket/services/alarm_queue.py](../../../../fastapi-server/websocket/services/alarm_queue.py) | 신규 |
| C4 | [fastapi-server/websocket/state.py](../../../../fastapi-server/websocket/state.py) | 수정 |
| C4 | [fastapi-server/internal/routers/alarm_router.py](../../../../fastapi-server/internal/routers/alarm_router.py) | 수정 |
| C4 | [fastapi-server/websocket/routers/ws_router.py](../../../../fastapi-server/websocket/routers/ws_router.py) | 수정 |
| C4 | [fastapi-server/websocket/services/broadcast.py](../../../../fastapi-server/websocket/services/broadcast.py) | 수정 |
| C4 | [fastapi-server/app.py](../../../../fastapi-server/app.py) | 수정 |
| C4 | [fastapi-server/core/config.py](../../../../fastapi-server/core/config.py) | 수정 (REDIS_URL) |
| C4 | [fastapi-server/requirements.txt](../../../../fastapi-server/requirements.txt) | 수정 (redis 추가) |
| C4 | [docker-compose.yml](../../../../docker-compose.yml) | 수정 (REDIS_URL + depends_on) |
| C5 | [drf-server/apps/alerts/tasks.py](../../../../drf-server/apps/alerts/tasks.py) | 수정 |

총 17 파일 (신규 5, 수정 12).
