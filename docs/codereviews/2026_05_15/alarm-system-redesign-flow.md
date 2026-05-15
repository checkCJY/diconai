# 알람 시스템 재설계 — 데이터 흐름 + 중요 함수 분석

작성일: 2026-05-15
대상 작업: Phase 1 (`feature/alarm-popup-refactory`) + Phase 2 (`feature/alarm-phase2-global-loading`) 총 10 commit
관련 문서: [`drf-server/docs/refactoring/alarm-system-redesign-2026-05-15.md`](../../../drf-server/docs/refactoring/alarm-system-redesign-2026-05-15.md) (배경·결정·검증)

본 문서는 **"코드가 어떻게 흐르는지"** 와 **"어떤 함수가 핵심인지"** 에 집중. 변경 의도·결정 근거는 위 refactoring 문서 참조.

---

## 1. 범위 — 변경 영역

```
drf-server (Django + DRF)                fastapi-server (FastAPI)
├── apps/alerts/                         ├── internal/routers/
│   ├── models/event_acknowledgement.py★ │   └── alarm_router.py ★
│   ├── selectors/event_ack_selector.py★ ├── websocket/
│   ├── services/event_service.py        │   ├── routers/ws_router.py
│   ├── views/event.py                   │   └── services/alarm_queue.py
│   ├── views/alarm_record.py            └── tests/test_push_alarm_dedup.py
│   └── tasks.py
├── apps/monitoring/services/{gas,power}_alarm.py
├── config/settings.py
├── static/js/shared/
│   ├── alarm-popup.js ★★ (가장 큰 변경)
│   ├── alarm-mapper.js
│   ├── alarm-ws.js
│   └── worker-ws.js
├── static/js/dashboard/websocket.js
├── static/css/alarm-popup.css ★ (신규)
└── templates/
    ├── components/alarm_stack.html ★
    ├── base/snb_base.html ★
    ├── admin_panel/base.html
    └── snb_details/*.html (7개)

★ 신규 ★★ 큰 변경
```

---

## 2. 데이터 흐름

알람 시스템은 4개 독립 흐름이 동시 동작. 각각 분리해서 추적.

### 2.1 일반 위험 알람 broadcast (가스/전력/지오펜스)

```
[시뮬레이터 또는 IoT]
     │ POST gas/power/positioning data
     ▼
[fastapi-server]
     │ services/gas_alarm·power_alarm 등에서 임계치 판정
     │ 위험 시 → drf_client.post_to_drf("/api/monitoring/.../alerts/")
     ▼
[drf-server]
     │ monitoring 측 view 가 fire_*_alarm_task.delay() 호출
     ▼
[Celery worker — apps/alerts/tasks.py]
     │ fire_danger_alarm_task / fire_geofence_alarm_task / fire_clear_*
     │ → create_alarm_and_event() [event_service.py]
     │     ├─ select_for_update 로 활성 Event 검색
     │     ├─ 활성 Event 있음 + 타임 윈도우 안 → AlarmRecord 만 추가 + last_detected_at 갱신
     │     │   + cooldown 초과면 last_notified_at 갱신 후 alarm 반환 (재알림)
     │     │   + cooldown 안이면 None 반환 (silent)
     │     └─ 없음 → Event + AlarmRecord 신규 생성 + AlertPolicy 자동 매칭
     │ ↑ Phase 1: cooldown = settings.ALARM_REPOPUP_COOLDOWN_SEC (env)
     ▼
[Celery worker — _push_to_ws(payload)]
     │ payload 구성 — event_id/alarm_type/risk_level/source_label/summary/message/is_new_event/worker_id
     │ ↑ Phase 1: worker_id 누락 fix (지오펜스 알람용)
     │ → POST http://fastapi:8001/internal/alarms/push/
     ▼
[fastapi alarm_router.push_alarm_handler]
     │ Bearer 토큰 / localhost 인증
     │ → push_alarm(payload) [alarm_queue.py]
     ▼
[push_alarm — Redis 큐 진입]
     │ _payload_fingerprint(payload) 계산
     │ ↑ Phase 1 fix: event_resolved_at 박혀있으면 event:{id}:resolved 별도 fp
     │ SET NX EX (dedup 30s) → 첫 도착자만 LPUSH
     │   "diconai:ws:alarms" LIST 좌측 push + LTRIM 10_000
     ▼
[alarm_flush_loop — ws_router.py:46]
     │ BRPOP(diconai:ws:alarms, timeout=0)
     │ → build_broadcast_payload(include_alarms=False)
     │ → base["alarms"] = [payload]
     │ → _send_to_all(base) → sensor_clients 전체에 send_json
     │
     │ 부수 분기 (alarm_type=geofence_intrusion + worker_id 박힘):
     │   worker_clients.get(worker_id) 의 WS 에도 type=worker_alert 로 전송
     ▼
[브라우저 — /ws/sensors/]
     │ ws-client.js 의 onMessage handler set 호출
     │ dashboard: dashboard/websocket.js
     │ admin-panel + snb_details: alarm-ws.js (alarm_stack 의 일부)
     │   ↓
     │ AlarmMapper.fromSensorsAlarm(raw) → 표준 모양 변환
     │ if (raw.is_new_event || raw.event_resolved_at) AlarmPopup.show(mapped)
     │ document.dispatchEvent('newAlarmEvent', { detail: mapped })  → event-panel.js 가 수신
     ▼
[AlarmPopup.show — alarm-popup.js:147]
     │ 1. _LastSeen.write — catch-up 기준점 갱신 (모든 path)
     │ 2. event_resolved_at 박혀있으면 → _handleResolved (별도 흐름 2.3)
     │ 3. ack skip — _AckStore.has(eventId) ? return
     │ 4. ↑ Phase 2: URL 이 /admin-panel/ → AlarmToastStack.push (별도 흐름 2.4)
     │ 5. group window — danger 1s / warning 5s 안에 같은 센서+레벨 → groupCount++
     │ 6. queue push + _process() → 중앙 차단형 모달 표시
```

### 2.2 user-scoped ack — "확인 완료" 클릭

```
[운영자가 모달의 "확인 완료" 클릭]
     ▼
[alarm-popup.js:init 의 confirm 핸들러]
     │ 1. _AckStore.add(eventId) — localStorage 즉시 저장 (서버 응답 안 기다림)
     │ 2. Auth.apiFetch('/alerts/api/events/{id}/ack/', method=POST) — fire-and-forget
     │ 3. AlarmPopup.close({ acknowledged: true })
     ▼
[drf — EventViewSet.ack action — views/event.py]
     │ IsAuthenticated permission
     │ EventAcknowledgement.objects.get_or_create(event, user=request.user)
     │ → { event_id, user_id, acknowledged_at, created } 반환
     ▼
[DB — event_acknowledgement 테이블]
     │ UniqueConstraint(event, user) → race 시에도 row 1건
```

다음 알람 수신 시:
- 같은 클라: `_AckStore.has(eventId) === true` → 팝업 skip (이벤트 패널은 newAlarmEvent 로 자연 표시)
- 다른 user 클라: 자기 _AckStore 에 없음 → 정상 팝업

### 2.3 RESOLVED 자동 close 흐름 (Phase 1 회색지대 결정)

```
[운영자가 event 상세 페이지에서 status → RESOLVED 변경]
     ▼
[drf — EventViewSet.update_status — views/event.py]
     │ status 전환 가능 검증 (ACTIVE/ACKNOWLEDGED → RESOLVED 허용)
     │ event.resolved_by = request.user
     │ event.resolved_at = timezone.now()
     │ event.save()
     │ EventLog.objects.create(action=RESOLVED, ...)
     │ ↓ Phase 1 신규 분기
     │ if new_status == RESOLVED:
     │     _push_to_ws({
     │         event_id, alarm_type, risk_level, source_label, summary,
     │         message: "위험 해소 — {source_label}",
     │         is_new_event: False,
     │         event_resolved_at: event.resolved_at.isoformat(),
     │     }, raise_on_failure=False)  # WS 실패가 트랜잭션 안 망치게
     ▼
[fastapi 의 흐름 2.1 의 push_alarm → broadcast — 단 fingerprint 분리]
     │ _payload_fingerprint → event:{id}:resolved (원래 알람과 별도)
     │ ↑ Phase 1 fix: 원래 알람과 같은 fp 라 dedup 차단되던 버그 해소
     ▼
[브라우저 — alarm-ws.js / dashboard/websocket.js]
     │ AlarmMapper.fromSensorsAlarm — event_resolved_at 필드 포함 매핑
     │ if (raw.is_new_event || raw.event_resolved_at) → AlarmPopup.show(mapped)
     ▼
[AlarmPopup.show — event_resolved_at 박혀있음]
     │ → AlarmPopup._handleResolved(mapped)
     │     ├─ 떠있는 _currentId === eventId 면 close({acknowledged:false})
     │     ├─ queue 에서 같은 event_id 제거
     │     └─ AlarmToast.show — 우하단 "위험 해소" 토스트 (5초)
```

### 2.4 admin-panel 토스트 stack (Phase 2 A-mini)

```
[admin-panel/* 페이지에서 알람 수신]
     ▼
[AlarmPopup.show — ack skip 직후 분기]
     │ if (!data.__forceModal && _resolveDisplayMode() === 'toast')
     │     → AlarmToastStack.push(data); return
     ▼
[AlarmToastStack.push]
     │ if _items.has(event_id) → return (중복 차단)
     │ _ensureContainer() — #alarm-toast-stack 동적 생성 (없으면)
     │ _createItem(data, level) — 빨강/노랑 색상 + 배지 + 메시지
     │ container.appendChild(item)
     │ item._timers = {
     │     dismiss: setTimeout(_dismiss, 15s/10s),
     │     escalate: setTimeout(→ AlarmPopup.show({...data, __forceModal:true}), 10s) (DANGER 한정)
     │ }
     │
     │ 사용자 액션:
     │   토스트 클릭 → dismiss + AlarmPopup.show({__forceModal:true}) (즉시 격상)
     │   ✕ 클릭     → dismiss (격상 X, 사용자가 인지)
     │   타임아웃   → dismiss (DANGER 면 동시에 격상 trigger)
```

### 2.5 페이지 로드 catch-up (Phase 1)

```
[브라우저 페이지 로드 → AlarmPopup.init()]
     │ ... event listeners 등록
     │ → this._runCatchUp() (비동기 fire)
     ▼
[_runCatchUp — alarm-popup.js]
     │ lastSeen = _LastSeen.read()  (localStorage)
     │ if (!lastSeen) return  (첫 방문 — catch-up 의미 없음)
     │ Auth.apiFetch(`/alerts/api/alarms/catch-up/?since=${lastSeen}`)
     ▼
[drf — AlarmRecordViewSet.catch_up — views/alarm_record.py]
     │ since float 파싱 (잘못된 값이면 빈 list)
     │ floor = now - 24h, since < floor 면 since = floor (클램프)
     │ AlarmRecord.objects.filter(created_at__gte=since).select_related("event")[:100]
     │ → broadcast payload 모양으로 변환 (event_id/alarm_type/.../is_new_event=False)
     ▼
[클라 — 받은 alarms 각각]
     │ window.dispatchEvent('newAlarmEvent', { detail: alarm })
     │   → event-panel.js 가 listener 로 받아 패널에 prepend
     │ _LastSeen.write(alarm.created_at)
     │
     │ AlarmPopup.show 직접 호출 X — is_new_event=false 라 자연 skip 의도
     │   (지나간 알람을 팝업으로 다시 띄우면 운영자 혼란)
```

---

## 3. 핵심 함수 list (위치 + 역할 + 의존성)

### 3.1 백엔드 (drf)

#### `apps/alerts/models/event_acknowledgement.py` ⭐ 신규

| 항목 | 내용 |
|---|---|
| 책임 | Event 의 user-scoped ack 영속화 |
| 핵심 제약 | `UniqueConstraint(event, user)` + 인덱스 `(user, -created_at)` |
| 호출자 | `EventViewSet.ack` action (get_or_create) |
| 조회자 | `get_acked_user_ids(event_id)` — broadcast hot path 헬퍼 |

#### `apps/alerts/views/event.py` — `EventViewSet.ack` + `update_status` ⭐

| 함수 | 라인 | 역할 |
|---|---|---|
| `ack(request, pk)` | (신규) | `EventAcknowledgement.objects.get_or_create(event, user=request.user)` |
| `update_status(request, pk)` | 변경 | RESOLVED 분기에서 `_push_to_ws` 호출 — broadcast trigger |

**의존성**: `from apps.alerts.tasks import _push_to_ws` (함수 안에서 import — circular 회피)

#### `apps/alerts/views/alarm_record.py` — `catch_up` action ⭐

| 입력 | `since` query (unix sec) |
|---|---|
| 처리 | float 파싱 → 24h 클램프 → AlarmRecord 24h 내 최대 100건 |
| 출력 | `{alarms: [{event_id, alarm_type, risk_level, ..., is_new_event:False}]}` (broadcast payload 모양) |
| 호출자 | 클라 `AlarmPopup._runCatchUp` |

#### `apps/alerts/services/event_service.py` — `create_alarm_and_event`

| 변경점 | `cooldown = timedelta(seconds=settings.ALARM_REPOPUP_COOLDOWN_SEC)` (기존 `minutes=1` 하드코드) |
|---|---|
| 정책 | env 변수로 운영 60s / 시연 15s 분기 가능 |

#### `apps/alerts/tasks.py` — `fire_geofence_alarm_task`

| 변경점 | `_push_to_ws` payload 에 `worker_id` 추가 |
|---|---|
| 효과 | fastapi `alarm_router` 의 `worker_clients[worker_id]` 분기가 비로소 동작 (끊어진 곳 #1) |

### 3.2 백엔드 (fastapi)

#### `internal/routers/alarm_router.py` — `AlarmPayload` 스키마

| 변경점 | `event_resolved_at: str | None = None` 필드 추가 |
|---|---|
| 모델 정책 | `extra: "ignore"` — drf 측이 정의되지 않은 필드 보내면 silent drop |
| 분기 | `alarm_type=="geofence_intrusion" + worker_id` → worker_clients 개인 전송 |

#### `websocket/services/alarm_queue.py` — `_payload_fingerprint`

| 변경점 | `event_id` 있고 `event_resolved_at` 박혀있으면 → `event:{id}:resolved` |
|---|---|
| 효과 | RESOLVED 신호가 원래 알람 fp 와 분리되어 30s dedup 안에 차단되지 않음 |
| 회귀 | `test_push_alarm_dedup.py` 3건 신규 (분리 보장 + retry idempotency 유지) |

#### `websocket/routers/ws_router.py` — `worker_stream` JWT 검증

| 변경점 | `str(payload.get("user_id")) != str(user_id)` (양쪽 str 변환) |
|---|---|
| 원인 | JWT user_id 는 string("13"), path param 은 int(13) → 항상 forbidden 무한 루프 |

### 3.3 클라이언트

#### `static/js/shared/alarm-popup.js` ⭐⭐ (가장 큰 변경)

| 모듈/메서드 | 역할 |
|---|---|
| `_AckStore` | localStorage `Map<event_id, ts>` + 24h pruning. has/add/_persist |
| `_LastSeen` | localStorage unix sec. catch-up since 기준점 |
| `_resolveDisplayMode()` | URL `/admin-panel/` 시작 → 'toast', 그 외 → 'modal' |
| `AlarmToastStack` | 우상단 토스트 stack 모듈 — push/_createItem/_dismiss + DANGER 격상 setTimeout |
| `AlarmPopup.show(data)` | **분기 hub**. 5단계: last_seen 갱신 → RESOLVED → ack skip → display_mode → group window → queue |
| `AlarmPopup._handleResolved(data)` | 같은 event_id 팝업 close + queue 제거 + 토스트 |
| `AlarmPopup._runCatchUp()` | init 시 fetch catch-up endpoint → newAlarmEvent dispatch |
| `AlarmPopup.init` | confirm 핸들러에 ack API 호출 + _AckStore.add + _runCatchUp 트리거 |

#### `static/js/shared/alarm-mapper.js`

| 변경점 | `_common()` return 에 `event_resolved_at: src.event_resolved_at \|\| null` 추가 |
|---|---|
| 의미 | RESOLVED 신호 필드가 mapper 통과 시 떨어지지 않도록 보장 |

#### `static/js/shared/alarm-ws.js` / `static/js/dashboard/websocket.js`

| 변경점 | 분기 조건에 `\|\| alarm.event_resolved_at` 추가 |
|---|---|
| 의미 | `is_new_event=false` 인 RESOLVED 신호도 `AlarmPopup.show` 호출 → `_handleResolved` 분기 |

### 3.4 인프라

| 파일 | 역할 |
|---|---|
| `templates/components/alarm_stack.html` ⭐ | DOM (alarm_popup include) + 알람 JS bundle 일괄. 한 줄 include 로 페이지 활성화 |
| `static/css/alarm-popup.css` ⭐ | dashboard.css 의 알람 selector 분리 + `#alarm-popup`/`#alarm-toast` 스코프 색상 변수 (자가완결) + 토스트 stack 스타일 |
| `templates/base/snb_base.html` ⭐ | snb_details 신규 페이지용 base. extends 만 하면 알람 인프라 자동 |

---

## 4. 코드 리뷰 관점

### 4.1 잘 된 점

- **진단 프레임**: "끊어진 6곳" 으로 작업 범위를 명확히 좁힌 점. 800줄 예상을 ~400줄로 축소.
- **회귀 가드**: 신규 17건 + 기존 회귀 영향 0. fix 가 다른 동작을 깨뜨리지 않음을 보장.
- **simplicity first 일관**: Phase 1 의 user-scoped ack 를 옵션 B (서버측 sensor_clients dict 재설계, ~110줄) 대신 옵션 A (클라 측 localStorage Set, ~30줄) 로 선택. 사용자 요구를 만족하면서 D-30 안전성 확보.
- **소스 단일화**: alarm-popup CSS 를 별도 파일로 분리해 자가완결 (스코프 변수 fallback). admin-panel·snb 페이지에 dashboard.css 전체 의존을 강제 안 함.
- **사전 버그 발견·인계**: 검증 중 발견한 사전 버그 2건 동봉 fix + monitoring_realtime 미해결 버그는 진단 인계.
- **stacked PR 분할**: Phase 1 → Phase 2 → Phase 3 분리로 review 부담 분산 + 시연 안전성.

### 4.2 잠재 리스크 / 트레이드오프

#### URL 기반 display_mode 분기
`_resolveDisplayMode` 가 `window.location.pathname.startsWith('/admin-panel/')` 로 분기. 향후 admin-panel 의 URL 구조 변경 시 깨짐. 대안은 body class 또는 context 변수지만 surgical 측면에서 URL 이 가장 단순.

#### dashboard vs alarm_stack 의 이중 인프라
`dashboard/main.html` 은 alarm_stack 안 쓰고 자체 인프라 유지. `dashboard/websocket.js` 가 sensor WS 의 모든 데이터 (가스/전력/알람/지오펜스) 통합 처리. 만약 alarm_stack 을 dashboard 에도 적용하면 onMessage handler 가 두 군데 (`alarm-ws.js` + `dashboard/websocket.js`) 등록되어 중복 호출. surgical 위반.
시연 후 정공법: `dashboard/websocket.js` 의 알람 처리 부분을 `alarm-ws.js` 와 통합 (책임 분리) — 별도 sprint.

#### 클라 측 ack store 의 다중 기기 한계
PC1 에서 ack → PC2 에서 같은 event 다시 표시. Phase 3 의 서버 측 라우팅 (옵션 B) 이 들어와야 다중 기기 일치. 단 본 작업에선 작업자 디바이스 미정으로 Phase 3 보류 상태.

#### 인증 가드 미적용
`alarm_stack.html` 에 `{% if user.is_authenticated %}` 가드 없음. diconai 가 JWT 인증이라 `user.is_authenticated` 가 항상 False 였기 때문. 비인증 페이지에 partial 가 들어가면 WS 401 close 자연 처리되지만, 시연 후 cookie 기반 JWT context_processor 도입 시 정교한 가드 추가 검토.

#### `_push_to_ws` 가 alerts.tasks 의 private 헬퍼
`EventViewSet.update_status` 의 RESOLVED 분기에서 `from apps.alerts.tasks import _push_to_ws` 로 import. underscore prefix 헬퍼를 view 에서 직접 import 하는 게 layer 측면에서 어색. 시연 후 정공법: services 레이어로 옮기거나 public 함수 노출.

#### dedup TTL 30s 와 cooldown 60s 의 race
fastapi `PUSH_DEDUP_TTL_SEC=30` 과 drf `ALARM_REPOPUP_COOLDOWN_SEC=60` (운영 기본) 이 다른 값. cooldown 안에 같은 event 의 retry 가 두 번 dedup 차단되는 게 의도 (운영 데이터 누적 전까지). 시연 모드에서 cooldown=15 면 dedup TTL 보다 짧아 race 가능성 미세 — 운영 환경 안전.

### 4.3 다음 작업자 가이드

| 시나리오 | 진입점 |
|---|---|
| 알람 동작 디버깅 | `alarm-popup.js:show()` 의 5단계 분기 순서대로 추적 (last_seen → RESOLVED → ack skip → display_mode → group window) |
| 알람 누락 의심 | fastapi 로그 `[push_alarm] dedup hit` → fingerprint 확인. Redis `LLEN diconai:ws:alarms` 큐 적체 확인 |
| 새 페이지에 알람 추가 | snb_details 신규 페이지면 `snb_base.html` extends. admin-panel 신규면 base 가 처리. 기타 페이지는 alarm_stack include 한 줄 |
| Phase 3 진입 시 | (작업자 디바이스 확정 후) `geofence/services/lookup.py` 신설 + `sensor_clients` 구조 재설계 + JWT 강제 활성 + drf `acked-users` API |
| monitoring_realtime fix | [`drf-server/docs/known-issues/monitoring-realtime-websocket-bug.md`](../../../drf-server/docs/known-issues/monitoring-realtime-websocket-bug.md) 의 fix 방향 옵션 4가지 참조 |

---

## 5. 부록 — 변수·메모리 위치 한눈에

### localStorage 키
| 키 | 값 | 위치 |
|---|---|---|
| `diconai:alarm:acked_event_ids` | `[{id, ts}, ...]` JSON | `_AckStore._persist` |
| `diconai:alarm:last_seen_ts` | unix sec | `_LastSeen.write` |
| `access_token` / `refresh_token` | JWT | `Auth` (기존) |

### Redis 키
| 키 | 타입 | 위치 |
|---|---|---|
| `diconai:ws:alarms` | LIST | alarm_queue.push_alarm / pop_alarm_blocking |
| `alarm:push:dedup:event:{id}:{risk}` | STRING (TTL 30s) | fingerprint dedup |
| `alarm:push:dedup:event:{id}:resolved` | STRING (TTL 30s) | RESOLVED 신호 별도 fp (Phase 1 신규) |

### Django settings
| 키 | 기본 | 시연 |
|---|---|---|
| `ALARM_REPOPUP_COOLDOWN_SEC` | 60s | 15s (.env.docker) |

### WS 채널
| 경로 | 용도 | client 측 |
|---|---|---|
| `/ws/sensors/` | 전체 broadcast (가스/전력/알람/위치) | sensor_clients list |
| `/ws/worker/{user_id}/` | 작업자 개인 (geofence_intrusion + ...) | worker_clients dict |
| `/ws/positions/` | 위치 데이터 | (별도) |
