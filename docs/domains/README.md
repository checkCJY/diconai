# 도메인 이해 문서

> 코드리뷰 전 흐름 파악용. 각 문서는 "파일맵 + 데이터 흐름 + 핵심 개념 + 리뷰 주의점" 구조.
> 주석 정비 작업(§6 컨벤션 적용) 중 파악한 각 도메인의 흐름을 정리한 것.

---

## 1. 두 서버의 책임 경계

| | drf-server (:8000) | fastapi-server (:8001) |
|---|---|---|
| 프레임워크 | Django + DRF (gunicorn, sync) | FastAPI (uvicorn, async) |
| 역할 | 인증·HTML·DB 영속성·REST·**알람 생성(Celery)** | 센서 수신·검증·**AI 추론**·**WS broadcast** |
| 상태 | DB (PostgreSQL) — 진실의 원천 | 프로세스 메모리(`websocket/state.py`) + Redis |
| 워커 | gunicorn 1 + threads 4 | **uvicorn 1** (단일 — broadcast 메모리 공유 전제) |

핵심 원칙: **fastapi 는 빠른 수신·전달, drf 는 영속·판정.** 알람 "생성"은 drf Celery 가, 알람 "전달"은 fastapi WS 가 책임.

---

## 2. 전체 데이터 흐름 (한 장)

```
[ 센서 ]  가스: HTTP 1초 │ 전력: HTTP │ 위치: WebSocket
   │
   ▼  ── fastapi-server (:8001) ──────────────────────────────────
      [수신·검증]
        POST /api/sensors/gas        gas_router   → GasDataPayload
        POST /api/power/{watt..}     power_router → Power*Payload
        WS   /ws/position/           ws_router.position_stream
            │
            ▼ [처리·AI]
        gas_service.process_gas_data        ← IF + ARIMA + CP (3축)
        power_service.process_anomaly_…     ← IF+ARIMA+Z+CP+night (5축)
            │
            ├─① 메모리 갱신: state.py (latest_gas_snapshot / power_latest /
            │     worker_positions) → broadcast_loop 가 주기적으로 읽어 전송
            │
            └─② DRF 저장 요청 (services/drf_client.post_to_drf)
   ───────────────────│───────────────────────────────────────────
                      │ POST (서버-서버 HTTP)
                      ▼
      ── drf-server (:8000) ──────────────────────────────────────
      [저장]
        POST /api/monitoring/gas/         GasDataCreateSerializer
        POST /api/monitoring/power/data/  PowerDataBulkIngestSerializer
        POST /api/positioning/receive/    handle_position_receive
            │ GasData / PowerData / WorkerPosition INSERT (PG)
            │
            ▼ [알람 판정]  (serializer.create 안에서 호출)
        gas_alarm.trigger_gas_alarms       9가스 루프
        power_alarm.trigger_power_alarms    16채널 × 3축 max
        position_service                    지오펜스 30px 근접 시
            │ try_transition (Redis Lua 원자 천이, 중복 fire 차단)
            │ AI mute 가드 (AI 발화 후 룰 60s 억제)
            ▼
        fire_*_task.delay()  ──────────────────────┐  (Celery 'alarm' 큐)
   ────────────────────────────────────────────────│──────────────
                                                    ▼
      ── Celery worker (drf 코드) ─────────────────────────────────
        fire_danger / warning / clear / power_* / geofence_alarm_task
            ① create_alarm_and_event()   ← Event 생성/병합 (DB 트랜잭션)
            ② _push_to_ws({event_id, risk_level, ...})
   ────────────────────────────│───────────────────────────────────
                               │ POST /internal/alarms/push/  (→ fastapi)
                               ▼
      ── fastapi-server (:8001) ──────────────────────────────────
        alarm_router.push_alarm_handler
            │ fingerprint dedup (Celery retry 중복 차단)
            ▼
        Redis LIST  LPUSH  "diconai:ws:alarms"
            ▼
        alarm_flush_loop  BRPOP (즉시 소비, 알람 경로)
        broadcast_loop    주기 송신 (BROADCAST_INTERVAL_SEC)
            │ _send_to_all(sensor_clients)   ← O(N) 직렬 전송
   ────────────────────────────│───────────────────────────────────
                               │ WebSocket /ws/sensors/
                               ▼
                        [ 브라우저 ]  WSClient (ws-client.js)
                                      → 패널 · 차트 · 알람팝업 · 맵
```

---

## 3. 단계별 상세

### ① 수신 (센서 → fastapi)
| 센서 | 프로토콜 | 엔드포인트 | 스키마 | 주기 |
|---|---|---|---|---|
| 가스 | HTTP POST | `/api/sensors/gas` | `GasDataPayload` (9종+LEL) | 1초 |
| 가스 기기정보 | HTTP POST | `/api/sensors/info` | `DeviceInfoPayload` | 부팅 1회 |
| 전력 | HTTP POST | `/api/power/{watt,current,voltage,onoff}` | `Power*Payload` (slave01~72) | — |
| 위치 | **WebSocket** | `/ws/position/` | `WorkerPositionSchema` | 이동 시 |

- 검증 시 **status/위험도 서버 재계산** (센서 펌웨어 불신). 가스는 `recalculate_status`, 전력은 `threshold_eval`.

### ② 처리·AI (fastapi 내부)
- 가스: co/h2s/co2 30틱 윈도우 → change point 게이트 → IF 추론 (3축).
- 전력: 채널별 IF+ARIMA+Z-score+ChangePoint+night = **5축** (`combine_risk_5axis`).
- AI 적중 시: `push_alarm` 직접(실시간) + DRF 에 ML 결과 forward + 룰 mute 마킹.

### ③ 메모리 갱신 → broadcast (fastapi, 알람과 별개 경로)
- `state.py` 의 `latest_gas_snapshot`/`power_latest`/`worker_positions` 를 처리 중 갱신.
- `broadcast_loop` 가 `BROADCAST_INTERVAL_SEC`(코드 기본 **5.0s**, env 로 조정)마다 `build_broadcast_payload()` 로 통합 dict 조립 → 전 클라이언트 전송. 알람은 이와 별개로 `alarm_flush_loop` 이 즉시 전달.
- **stale 처리**: 마지막 갱신이 `DATA_STALE_THRESHOLD_SEC`(기본 **8.0s**) 초과면 해당 영역 None/로딩 (가짜 더미값 표시 방지).

### ④ 저장 (fastapi → drf, 서버-서버 HTTP)
| 데이터 | 엔드포인트 | 시리얼라이저 | 특징 |
|---|---|---|---|
| 가스 | `POST /api/monitoring/gas/` | `GasDataCreateSerializer` | wide table 1행, last_reading 60s 스로틀 |
| 전력 측정 | `POST /api/monitoring/power/data/` | `PowerDataBulkIngestSerializer` | 16채널 bulk_create (ignore_conflicts) |
| 전력 ON/OFF | `POST /api/monitoring/power/event/` | `PowerEventIngestSerializer` | 스냅샷 + changed_channels |
| 위치 | `POST /api/positioning/receive/` | — | 항상 저장(이력 보존) |

- `services/drf_client.post_to_drf` 가 호출. 실패 시 fastapi 가 센서에 502/503 전파.

### ⑤ 알람 판정 (drf, serializer.create 안에서)
- 가스 9가스 / 전력 16채널×3축 루프. `try_transition`(Redis Lua) 으로 **동시 중복 fire 차단**.
- AI mute 가드: AI 가 발화한 (센서·채널) 은 룰 알람 60s 억제 (AI 우선).
- 위험도별 `fire_*_task.delay()` → Celery 큐(`alarm`).

### ⑥ 알람 생성 (Celery worker, drf 코드)
- `create_alarm_and_event`: 활성 Event 병합(12h 윈도우) 또는 신규 생성. 쿨다운(60s) / 격상(즉시) 분기. → [alerts.md](alerts.md) §3.
- DB 커밋 후 `_push_to_ws` → `POST /internal/alarms/push/` (fastapi).

### ⑦ 전달 (fastapi → 브라우저)
- `push_alarm_handler`: fingerprint dedup 후 Redis LIST `diconai:ws:alarms` LPUSH.
- `alarm_flush_loop`: BRPOP 즉시 소비 → `_send_to_all`. 클라이언트 없으면 큐에 **보존**(유실 방지).
- 브라우저 `WSClient`(`/ws/sensors/`) 가 수신 → 패널/차트/알람팝업 갱신.

---

## 4. 주요 Redis 키 / 상수

| 키·상수 | 값 | 용도 | 위치 |
|---|---|---|---|
| `diconai:ws:alarms` (LIST) | — | 알람 전달 큐 (LPUSH/BRPOP) | fastapi alarm_queue |
| `alarm:state:{sensor}:{gas}` | — | 가스 알람 상태 (try_transition) | drf gas_alarm |
| `alarm:power:state:{dev}:{ch}` | — | 전력 알람 상태 | drf power_alarm |
| `ai_fired:{dev}:{ch}:{lv}` / `ai_fired_gas:{sensor}:{gas}:{lv}` | — | AI mute 마킹 | fastapi ai_mute ↔ drf alarm_dedupe |
| `ALARM_REPOPUP_COOLDOWN_SEC` | 60 | 재알림 쿨다운 | drf settings |
| `WARNING_DURATION_SEC` | 3 | WARNING 지속 타이머 | drf tasks |
| `BROADCAST_INTERVAL_SEC` | 5.0 | broadcast 주기 (코드 기본, env 조정) | fastapi config |
| `DATA_STALE_THRESHOLD_SEC` | 8.0 | stale 판정 임계 | fastapi config |

---

## 5. 동시성·정합성 포인트 (리뷰 핵심)

1. **try_transition (Redis Lua)** — GET+CMP+SET 원자화로 동시 중복 fire 차단. [alerts.md](alerts.md) §6.
2. **fingerprint dedup** — Celery retry 가 같은 알람 N번 push 하는 것 차단 (30s TTL).
3. **DB/WS try 분리** — DB 커밋 후 WS 실패해도 retry 안 함 (AlarmRecord 중복 방지). DB 가 진실의 원천.
4. **AI mute 키 식별자 일치** — fastapi(mac) ↔ drf(mac) 같은 키여야 가드 동작. PK 혼용 시 중복 발화. [power.md](power.md) §8.
5. **단일 워커 전제** — broadcast/개인알림이 메모리 공유에 의존. 멀티워커 전환은 `skill/plan/fastapi-multiworker-redis-pubsub.md`.

---

## 6. 도메인별 문서

| 문서 | 도메인 | 한 줄 |
|---|---|---|
| [gas.md](gas.md) | 가스 모니터링 | 9종 가스 수신 → 룰+IF 판정 → 알람 |
| [power.md](power.md) | 전력 모니터링 | 16채널 3축 → **5축 AI** 판정 → 알람 |
| [ai-ml.md](ai-ml.md) | AI/ML | drf 학습 ↔ fastapi 추론 분리 |
| [alerts.md](alerts.md) | 알람 | **가스·전력·지오펜스 공유 수렴점** |
| [positioning.md](positioning.md) | 작업자 위치 | 위치 저장 + 지오펜스 진입 알람 |
| [websocket.md](websocket.md) | 프론트 WS | WSClient 단일 래퍼 |

### 읽는 순서 (추천)
1. **이 README** — 전체 흐름 그림.
2. **alerts.md** — 모든 센서가 모이는 수렴점. 알람 모델(AlarmRecord/Event) 먼저 이해.
3. **gas.md** — 가장 단순한 end-to-end.
4. **power.md** — 가스 위 5축 AI.
5. **ai-ml.md / positioning.md / websocket.md** — 나머지 가지.

## 7. 관련 컨벤션·plan
- 주석/docstring 규약: [../conventions/dev_convention.md](../conventions/dev_convention.md) §6
- 멀티워커 전환 설계: `skill/plan/fastapi-multiworker-redis-pubsub.md` (시연 후 착수 보류)
