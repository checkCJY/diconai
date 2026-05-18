# 알람 시스템 재설계 — Phase 1 + Phase 2

작성일: 2026-05-15
브랜치: `feature/alarm-popup-refactory` (Phase 1), `feature/alarm-phase2-global-loading` (Phase 2, stacked)
관련 PR: 본 문서 작성 시점에 push 전 — 시연 직전 push 예정

---

## 개요

PR #57 (`feat(dashboard): 이벤트 현황 패널 원안 디자인 + 정상화 dedup·burst 그룹화 + message 일관화`) 머지 직후 사용자 피드백:

1. **위험 상태 지속 중 "확인 완료" 후 다시 위험이면 팝업이 재표시되어야 함**
2. **대시보드 외 다른 페이지에서도 위험 알람 팝업이 즉시 떠야 함**
3. **알람 발생 비즈니스 로직에 권한 분기 — 관리자=전체 / 작업자=본인 지오펜스 영역만 + 대피 안내**

이에 대응하여 알람 인프라를 **단계적**으로 재설계. 한 PR 에 모두 넣지 않고 Phase 1 / Phase 2 / Phase 3 분할 — 시연 D-30 (2026-06-14) 안전성 + PR review 부담 분산.

### 진단 프레임 — "인프라 깔려있고 연결 끊어진 6곳"

조사 결과 권한 모델·worker_clients 채널·Event 상태 변경 API 같은 인프라는 대부분 구축되어 있었고, 연결만 끊어진 곳이 6곳으로 좁혀짐. 초기 추정 800줄 → 실제 ~400줄로 surgical 작업 가능.

| # | 끊어진 곳 | 사용자가 본 현상 | Phase 1 | Phase 2 | Phase 3 보류 |
|---|---|---|:---:|:---:|:---:|
| 1 | Celery payload 의 `worker_id` 누락 | 지오펜스 알람이 broadcast 만, 개인 채널 미동작 | ✅ | | |
| 2 | "확인 완료" 가 백엔드 API 미호출 | Event 상태가 ACKNOWLEDGED 로 안 바뀜, 운영 이력 누락 | ✅ | | |
| 3 | 같은 센서+레벨 5초 group 윈도우가 위험 알람도 silent | 위험 지속 중 재발생 시 팝업 재표시 X | ✅ | | |
| 4 | `alarm-ws.js` 페이지별 로딩 불완전 | dashboard 외 페이지에서 팝업 안 뜸 | | ✅ | |
| 5 | 가스/전력 센서 → 지오펜스 역조회 함수 없음 | 작업자에게 본인 영역 가스/전력 위험만 보내기 불가 | | | ⏸ |
| 6 | `/ws/sensors/` 권한 분기 없음 | 모든 user 가 모든 알람 받음 | | | ⏸ |

**Phase 3 보류 이유** (2026-05-15 사용자 확정): 작업자 알람 수신 **디바이스 종류·UX 가 미정**. 디바이스 결정 전 권한별 라우팅 구현 시 디바이스 결정 후 재작업 위험. 현재는 sensor broadcast 로 모든 인증 user 가 알람 받음 — 시연 충분 + "개개인별 라우팅은 고도화" 멘트로 자연 처리.

---

## Phase 1 — 알람 인프라 정비 + 사용자 요구 #1 대응

브랜치: `feature/alarm-popup-refactory`
commit 수: 5
변경 라인: 백엔드 ~400줄 + 회귀 테스트 17건 신규

### 1.1 user-scoped acknowledgement (끊어진 곳 #2)

#### 문제
`Event.status = ACKNOWLEDGED` 는 글로벌 단일 상태였음. 한 운영자가 확인하면 모든 user 에게 "확인됨" 으로 표시되어 다른 운영자가 알람을 못 봄.

#### 해결
별도 join 테이블 `EventAcknowledgement(event, user, acknowledged_at)` 신설. Event.status 와 무관하게 user 단위로 ack 기록.

| 신규 파일 | 역할 |
|---|---|
| `apps/alerts/models/event_acknowledgement.py` | `UniqueConstraint(event, user)` + 인덱스 `(user, -created_at)` |
| `apps/alerts/migrations/0015_eventacknowledgement.py` | 테이블 신설 |
| `apps/alerts/selectors/event_ack_selector.py` | `get_acked_user_ids(event_id) -> set[int]` 헬퍼 |
| `apps/alerts/views/event.py` | `ack` action 추가 (`POST /alerts/api/events/{id}/ack/`) |

API:
```http
POST /alerts/api/events/{id}/ack/
→ {
    "event_id": 42,
    "user_id": 5,
    "acknowledged_at": "2026-05-15T10:30:00+09:00",
    "created": true   # 첫 ack 면 true, 이미 ack 했으면 false (idempotent)
  }
```

### 1.2 재팝업 cooldown env 변수화

기존 `RENOTIFY_COOLDOWN_MINUTES = 1` 하드코드 → `settings.ALARM_REPOPUP_COOLDOWN_SEC` 환경변수.

| 변경 파일 | 변경 내용 |
|---|---|
| `config/settings.py` | `ALARM_REPOPUP_COOLDOWN_SEC = env.int(..., default=60)` |
| `apps/alerts/services/event_service.py` | `timedelta(seconds=settings.ALARM_REPOPUP_COOLDOWN_SEC)` |
| `.env.docker` 운영자 설정 | 시연 모드 시 `ALARM_REPOPUP_COOLDOWN_SEC=15` |

`docker compose restart drf` 가 아닌 `up -d drf` 로 env_file 재주입 필요 (운영 노트).

### 1.3 RESOLVED 자동 close (회색지대 결정)

운영자가 Event 를 RESOLVED 로 변경 시 떠있는 팝업이 자동 close + "위험 해소" 토스트 표시.

| 변경 | 위치 |
|---|---|
| `AlarmPayload` 에 `event_resolved_at: str | None` 필드 추가 | `fastapi-server/internal/routers/alarm_router.py` |
| `update_status` view 의 RESOLVED 분기에서 `_push_to_ws` 호출 | `apps/alerts/views/event.py` |
| 클라 `_handleResolved` 메서드 — 같은 event_id 팝업 close + 토스트 | `static/js/shared/alarm-popup.js` |
| `AlarmMapper._common()` 에 `event_resolved_at` 매핑 추가 | `static/js/shared/alarm-mapper.js` |
| `alarm-ws.js` / `dashboard/websocket.js` 분기에 `\|\| event_resolved_at` 추가 | (해당 두 파일) |

### 1.4 페이지 로드 시점 catch-up endpoint

WS 끊김 중 발생한 알람을 페이지 새로고침·재진입 시 보충. (WS reconnect hook 자체는 Phase 2 의 WS 안정성 task — 시연 후 PR 예정)

| 신규 | 위치 |
|---|---|
| `GET /alerts/api/alarms/catch-up/?since=<unix_ts>` action | `apps/alerts/views/alarm_record.py` |
| 클라 `_runCatchUp` 메서드 (init 시 호출) | `static/js/shared/alarm-popup.js` |
| 클라 `_LastSeen` localStorage 헬퍼 | (alarm-popup.js 안) |

응답 형식: fastapi broadcast payload 와 동일 (`event_id`/`alarm_type`/`risk_level`/`source_label`/`summary`/`message`/`is_new_event=false`/`created_at`). 24h 클램프 + 최대 100건.

### 1.5 group 윈도우 위험 알람 1초 단축

기존 5초 group 윈도우가 위험 알람도 silent groupCount++ 처리 → 위험 지속 중 재팝업 안 됨. 위험 알람만 1초로 단축, 주의는 5초 유지 (전기 노이즈 burst 보호).

```js
const windowMs = (level === 'danger') ? 1000 : this.GROUP_WINDOW_MS;
```

### 1.6 클라 측 user-scoped ack store (옵션 A)

서버 측 `sensor_clients` 구조 재설계 (옵션 B) 는 작업량이 Phase 3 의 대부분을 당겨오는 규모라 시연 D-30 부담. 시연 안전 + 작업량 ~30줄 의 절충안으로 클라 측 localStorage Set + ack API 이중.

| 신규 모듈 | 동작 |
|---|---|
| `_AckStore` | localStorage `Map<event_id, ts>` + 24h pruning |
| `_LastSeen` | localStorage `last_seen_ts` (catch-up since 기준점) |

알람 수신 시 `_AckStore.has(eventId)` 면 본인 클라에서만 skip → "본 사람만 안 보임, 다른 사용자에게는 계속 뜸" 만족.

Phase 3 의 옵션 B (서버측 라우팅) 가 들어오면 이 Set 은 보강재로 유지 (다중 기기 race 가드).

### 1.7 worker_id payload 누락 fix (끊어진 곳 #1)

지오펜스 진입 알람 (`fire_geofence_alarm_task`) 의 `_push_to_ws` payload 에 `worker_id` 가 누락되어 fastapi `alarm_router` 의 worker_clients 개인 채널 분기가 동작 안 했음. payload 1줄 추가.

```python
_push_to_ws({
    "event_id": event.id,
    "alarm_type": AlarmType.GEOFENCE_INTRUSION,
    ...
    "worker_id": worker_id,   # 추가 (Phase 1)
})
```

### 1.8 사전 버그 동봉 fix

#### 1.8.1 `/ws/worker/{user_id}/` JWT type mismatch
JWT payload 의 `user_id` 는 string `"13"`, FastAPI path param 은 int `13`. `"13" != 13` → 항상 forbidden → worker-ws.js 가 매초 재연결 무한 루프 + fastapi 로그 폭주 + sensor broadcast hot path 간섭.

```python
# fastapi-server/websocket/routers/ws_router.py
- if payload and payload.get("user_id") != user_id:
+ if payload and str(payload.get("user_id")) != str(user_id):
```

#### 1.8.2 alarm dedup fingerprint 가 RESOLVED 신호 차단
`_payload_fingerprint` 가 `event:{id}:{risk_level}` 로 생성하는데, RESOLVED 신호도 원래 알람과 같은 `event_id` + `risk_level` 조합이라 30초 dedup TTL 안에 hit 되어 broadcast 차단됨. 검증 5 의 root cause.

```python
# fastapi-server/websocket/services/alarm_queue.py
if event_id is not None:
    if payload.get("event_resolved_at"):
        return f"event:{event_id}:resolved"
    return f"event:{event_id}:{risk_level}"
```

### 1.9 회귀 테스트 신규 17건

| 파일 | 검증 |
|---|---|
| `test_event_acknowledgement.py` (5) | UniqueConstraint / ack API idempotent / 401 / user-scoped selector / cooldown env 존재 |
| `test_resolved_broadcast.py` (3) | RESOLVED → _push_to_ws + payload / ACKNOWLEDGED·IN_PROGRESS 미호출 |
| `test_alarms_catch_up.py` (6) | since 필터 / 24h 클램프 / payload shape / since 누락·invalid / 100건 cap |
| `test_push_alarm_dedup.py` 에 추가 (3) | RESOLVED 신호 별도 fingerprint / 원래 알람과 둘 다 LPUSH / RESOLVED 신호 retry idempotency |

### Phase 1 commit 목록

```
b058b19 feat(alerts): user-scoped ack + RESOLVED 자동 close 인프라
d51db0b feat(alerts): 재팝업 cooldown env 변수화 + 작업자 worker_id payload
a9798e5 feat(alerts): WS 재연결 catch-up endpoint (since= 필터링)
b41e7b6 feat(dashboard): 알람 팝업 user-scoped ack + RESOLVED auto-close + catch-up 통합
e1d26ce fix(fastapi): /ws/worker JWT type mismatch + alarm dedup RESOLVED fingerprint 분리
```

---

## Phase 2 — 미적용 페이지 인프라 확장 + admin-panel UX 차별화

브랜치: `feature/alarm-phase2-global-loading` (Phase 1 stacked)
commit 수: 4
변경 라인: ~250줄

### 2.1 공통 alarm partial 신설

| 신규 파일 | 역할 |
|---|---|
| `templates/components/alarm_stack.html` | alarm_popup.html DOM + 알람 JS bundle 일괄 (auth, ws-client, level-mapper, time-format, alarm-mapper, alarm-popup, alarm-ws, worker-ws) |
| `static/css/alarm-popup.css` | dashboard.css 의 알람 selector 분리, 자가완결 (`#alarm-popup` / `#alarm-toast` 스코프 색상 변수) |

인증 가드 (`{% if user.is_authenticated %}`) 미적용 — diconai 가 JWT 인증이라 template context 의 `user.is_authenticated` 가 항상 False 됨. 인증 경계는 view 단 redirect 가 담당.

### 2.2 적용 범위

| 페이지 그룹 | Phase 2 변경 | 비고 |
|---|---|---|
| `admin_panel/*` | ✅ `admin_panel/base.html` 에 partial include + 기존 `auth.js`/`ws-client.js` 중복 제거 | admin-panel 전체 자동 적용 |
| snb_details 7개 | ✅ partial 직접 include | `monitoring_gas/power/workers`, `my_profile`, `safety_checklist/history/vr` |
| `dashboard/main.html` | ⏭ 변경 없음 | `dashboard/websocket.js` 통합 처리 — alarm-ws.js 와 onMessage 중복 위험 |
| `monitoring_events` / `event_detail` | ⏭ 변경 없음 | 이미 알람 인프라 보유 |
| `monitoring_realtime` | ⛔ 제외 | 사전 버그 (3 참조) |

### 2.3 snb_base.html (C-mini)

기존 snb_details 10개 페이지가 자체 완결 HTML (extends 없음) 이라 새 페이지 추가 시마다 alarm_stack include 누락 위험. 신규 페이지용 base 신설.

| 신규 | 위치 |
|---|---|
| `templates/base/snb_base.html` | extends 대상. 공통 head/body + alarm_stack 자동 include + extra_css/extra_js block 제공 |

기존 10개 페이지 마이그레이션은 시연 D-30 안전 우선으로 보류 — 시연 후 별도 PR.

### 2.4 admin-panel UX 차별화 (A-mini)

사용자 피드백: "차단형 모달은 admin-panel 에서 비추. 폼 작성 중 입력 손실 + 운영자가 무지성 닫기 학습 → 진짜 위험이 가장 무시당하는 역설."

| 변경 | 동작 |
|---|---|
| `_resolveDisplayMode()` — URL 기반 분기 | `/admin-panel/` 으로 시작 → 'toast', 그 외 → 'modal' (기존 동작) |
| `AlarmToastStack` 모듈 | 우상단 fixed 컨테이너에 토스트 누적, slide-in/out 애니메이션 |
| 자동 dismiss | DANGER 15s / WARNING 10s |
| DANGER 격상 | 10s 무응답 → `__forceModal: true` 플래그로 같은 데이터 modal 재진입 |
| 토스트 클릭 | 즉시 모달로 전환 (사용자 인지 시그널) |

CSS 의 토스트 스타일은 `#alarm-toast-stack` + `.alarm-toast-stack-item` 셀렉터. dashboard 페이지 영향 0 (URL 분기로 자연 skip).

### 2.5 사전 버그 인계

`monitoring_realtime` 페이지가 `dashboard/websocket.js` 를 그대로 로드하지만 `charts.js`·`event-panel.js` 미로드 → `powerChart`/`gasChart`/`EventPanel` 미선언 상태 접근 → `ReferenceError` → onMessage handler 중단 → 알람 처리 미실행.

다른 팀원 작업 영역이라 진단만 인계.

- 진단 문서: `drf-server/docs/known-issues/monitoring-realtime-websocket-bug.md`
- 시연 시나리오 제외

### Phase 2 commit 목록

```
cad8c9f feat(dashboard): 공통 알람 partial alarm_stack 신설 + admin-panel/snb_details 전 페이지 적용
54d581f feat(dashboard): snb_details 신규 페이지용 공통 base 신설 (C-mini)
f3b7781 feat(dashboard): admin-panel UX 차별화 — 토스트 stack + DANGER 10초 격상 (A-mini)
f8c5de4 docs(known-issues): monitoring_realtime 페이지 진단 인계
```

---

## 사용자 요구 vs 진행 상황

| 요구 | Phase | 상태 |
|---|---|---|
| ① 위험 지속 중 "확인 완료" 후 재팝업 | Phase 1 | ✅ user-scoped ack + cooldown env + 5초 윈도우 위험 1초 |
| ② 다른 페이지에서도 알람 팝업 | Phase 2 | ✅ alarm_stack partial + admin-panel + snb_details 7개 |
| ③ 권한별 분기 (작업자 = 본인 영역만) | Phase 3 | ⏸ 작업자 디바이스 UX 미정 → 디바이스 확정 후 별도 sprint |

---

## 시연 시나리오 (S1, S2', S3, S4)

### S1 — 관리자 dashboard: 확인 → 재팝업 → 해소
1. dashboard 접속 → 시뮬레이터 위험 알람 → 중앙 차단형 모달
2. "확인 완료" → `EventAcknowledgement` row 생성 + 로컬 Set 저장
3. 위험 지속 → cooldown 후 새 AlarmRecord → broadcast → 새 팝업 (다른 사용자 클라에도)
4. 운영자 RESOLVED → 모든 클라 팝업 자동 close + "위험 해소" 토스트
5. 패널에 정상화 burst 그룹화 ("외 N건")

### S2' — Phase 2 작업자 stub 멘트
시연에서 작업자 단말 별도 노출 시:
> "작업자도 dashboard 페이지에서 알람을 수신합니다. 개개인별 라우팅 (본인 지오펜스 한정 + 대피 안내) 은 작업자 디바이스 확정 후 별도 sprint 에서 구현 예정입니다."

### S3 — admin-panel: 폼 작성 중 알람 (Phase 2)
1. admin-panel/notices/create/ 진입 → 공지 작성 시작
2. 시뮬레이터 위험 알람 → 우상단 토스트 (입력 손실 X)
3. 폼 작성 계속 가능
4. 10초 무응답 시 → 차단형 모달 격상 → 운영자 인지
5. "확인 완료" → 폼 그대로 살아있음

### S4 — 페이지 이동·새로고침 catch-up (Phase 1)
1. dashboard 알람 받은 후 페이지 새로고침
2. `GET /alerts/api/alarms/catch-up/?since={last_seen_ts}` 호출
3. 미수신 알람 (있다면) → 이벤트 패널에 누적 (`is_new_event=false` 이라 팝업 자연 skip)
4. Console: `[AlarmPopup] catch-up: N missed alarms restored`

---

## 검증 결과

### 자동 회귀
- DRF 신규 회귀 14건 통과 + 기존 회귀 영향 없음
- FastAPI 신규 회귀 3건 통과 + 기존 영향 없음

### 브라우저 검증
| # | 페이지 | 결과 |
|---|---|---|
| 1 | `/dashboard/` super_admin → 모달·재팝업·RESOLVED | ✅ 통과 |
| 2 | `/admin-panel/notices/`, `accounts-management/` super_admin → 토스트·격상 | ✅ 통과 |
| 3 | `/dashboard/monitoring/realtime/` super_admin | ⛔ 사전 버그 — 시연 제외 |
| 4 | `/dashboard/safety/checklist/` worker | ✅ 통과 |
| 5 | 페이지 새로고침 → catch-up endpoint | ✅ 통과 |

---

## 미완료·보류 항목

### Phase 3 (작업자 디바이스 확정 후 별도 sprint)
- 끊어진 곳 #5 — 가스/전력 센서 → 지오펜스 역조회 함수 (`apps/geofence/services/lookup.py`)
- 끊어진 곳 #6 — `/ws/sensors/` 권한 분기 (`sensor_clients` dict 재설계 + JWT 강제 활성)
- 클라이언트 측 user-scoped ack (옵션 A) → 서버 측 (옵션 B) 마이그레이션

### 시연 후 PR 옵션
- WS 안정성 — 토큰 만료 재연결 + 폴링 fallback (~80줄)
- snb_details 기존 10개 페이지 → snb_base.html extends 마이그레이션

### 다른 팀원 인계 (사전 버그)
- `monitoring_realtime` 페이지의 dashboard/websocket.js 의존성 누락 → 진단 문서 참조

### docs/skill 외 stale 도큐먼트
- `skill/알람 시나리오 관련 파일과 흐름도.md` 의 WebSocket 섹션이 옛 5초 폴링 설계로 작성 (현재는 Redis BRPOP 즉시 broadcast). 시연 후 별도 PR `docs: 알람 흐름도 Redis 기반 broadcast 반영` 권장.

---

## 관련 파일 목록

### Phase 1 신규
- `apps/alerts/models/event_acknowledgement.py`
- `apps/alerts/migrations/0015_eventacknowledgement.py`
- `apps/alerts/selectors/event_ack_selector.py`
- `apps/alerts/tests/test_event_acknowledgement.py`
- `apps/alerts/tests/test_resolved_broadcast.py`
- `apps/alerts/tests/test_alarms_catch_up.py`

### Phase 1 변경
- `apps/alerts/models/__init__.py` (EventAcknowledgement 등록)
- `apps/alerts/views/event.py` (ack action + RESOLVED 분기)
- `apps/alerts/views/alarm_record.py` (catch-up action)
- `apps/alerts/services/event_service.py` (cooldown env)
- `apps/alerts/tasks.py` (worker_id payload)
- `apps/monitoring/services/gas_alarm.py` / `power_alarm.py` (주석 정합성)
- `config/settings.py` (ALARM_REPOPUP_COOLDOWN_SEC)
- `static/js/shared/alarm-popup.js` (_AckStore, _LastSeen, _handleResolved, _runCatchUp, group window)
- `static/js/shared/alarm-mapper.js` (event_resolved_at 매핑)
- `static/js/shared/alarm-ws.js` (RESOLVED 분기)
- `static/js/dashboard/websocket.js` (RESOLVED 분기)
- `fastapi-server/internal/routers/alarm_router.py` (event_resolved_at 필드)
- `fastapi-server/websocket/routers/ws_router.py` (JWT type fix)
- `fastapi-server/websocket/services/alarm_queue.py` (RESOLVED fingerprint)
- `fastapi-server/tests/test_push_alarm_dedup.py` (회귀 3건 추가)

### Phase 2 신규
- `templates/components/alarm_stack.html`
- `templates/base/snb_base.html`
- `static/css/alarm-popup.css`
- `drf-server/docs/known-issues/monitoring-realtime-websocket-bug.md`

### Phase 2 변경
- `templates/admin_panel/base.html` (partial include + 중복 JS 제거)
- `templates/snb_details/*.html` 7개 (partial include)
- `static/js/shared/alarm-popup.js` (`_resolveDisplayMode` + `AlarmToastStack`)
