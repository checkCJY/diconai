# D 옵션 본격 — 데이터 흐름 + 중요 함수 분석

작성일: 2026-05-17
대상 작업: `feature/alarm-phase2-global-loading` 의 commit `e9c930e` (단일 commit)
관련 문서: [`drf-server/docs/refactoring/alarm-d-option-2026-05-17.md`](../../../drf-server/docs/refactoring/alarm-d-option-2026-05-17.md) — 배경·결정·검증

본 문서는 **"코드가 어떻게 흐르는지"** 와 **"어떤 함수가 핵심인지"** 에 집중. 변경 의도·결정 근거는 위 refactoring 문서 참조.

---

## 1. 범위 — 변경 영역

```
drf-server (Django + DRF)                Frontend (static + templates)
├── apps/alerts/                         ├── static/js/shared/
│   ├── selectors/                       │   ├── alarm-badge.js ★★ (신규)
│   │   └── event_ack_selector.py ★     │   └── alarm-popup.js ★ (_DedupStore + race fix)
│   └── views/                           ├── static/css/
│       └── alarm_record.py ★           │   ├── components/header.css ★
                                        │   └── admin.css ★
                                        └── templates/
                                            ├── components/header.html ★
                                            ├── components/alarm_stack.html ★
                                            ├── dashboard/main.html ★
                                            └── admin_panel/base.html ★

★★ 큰 변경 / 신규 ★ 부분 변경
```

---

## 2. 데이터 흐름

D 옵션 작업은 **4 개의 독립 흐름** + **1 개의 race 디버깅 케이스** 로 분리해서 추적.

### 2.1 페이지 진입 — 헤더 배지 초기값 fetch

```
[DOMContentLoaded fire]
     │
     ▼
[AlarmBadge.init() — alarm-badge.js]
     │ _resolveEls() — #btnAlarmBadge + .alarm-badge-count 존재 확인
     │ if (!found) return ← 헤더 없는 페이지 (로그인 등) silent skip
     │
     │ _btnEl.addEventListener('click', _onBadgeClick)
     │ document.addEventListener('newAlarmEvent', _onNewAlarm)
     │ window.addEventListener('newAlarmEvent', _onNewAlarm)
     │ _fetchInitial()
     ▼
[_fetchInitial() — async]
     │ Auth.apiFetch('/alerts/api/alarms/summary/')
     ▼
[drf-server — AlarmRecordViewSet.summary]
     │ from apps.alerts.selectors.event_ack_selector import get_user_unread_event_count
     │ user_unread = get_user_unread_event_count(request.user.id)
     ▼
[selectors/event_ack_selector.get_user_unread_event_count]
     │ Event.objects
     │     .filter(status__in=[ACTIVE, ACKNOWLEDGED, IN_PROGRESS])
     │     .exclude(event_acknowledgements__user_id=user_id)  ← NOT EXISTS subquery
     │     .count()
     │ ↑ EventAcknowledgement.UniqueConstraint(event, user) 인덱스 자동 활용
     ▼
[Response — JSON]
     │ { ..., user_unread_event_count: 3 }
     ▼
[_fetchInitial 응답 처리]
     │ n = Number(data.user_unread_event_count)
     │ _count = Math.max(_count, n)  ← race 보정 (catch-up dispatch 가 먼저 발생했을 수 있음)
     │ _render()
     ▼
[_render() — DOM 반영]
     │ if (_count <= 0) _countEl.hidden = true  ← 종만 (회색)
     │ else _countEl.hidden = false + textContent = _count > 99 ? '99+' : count
```

### 2.2 새 알람 도착 — 헤더 카운터 ↑

```
[WS sensors 채널 (또는 worker)]
     │ 알람 도착
     ▼
[alarm-ws.js / worker-ws.js / alarm-popup.js (catch-up)]
     │ document.dispatchEvent(new CustomEvent('newAlarmEvent', { detail: data }))
     │ 또는 window.dispatchEvent (catch-up 의 경우)
     ▼
[AlarmBadge._onNewAlarm] ← document/window 양쪽 listen 등록됨
     │ _count += 1
     │ _render()
     ▼
[DOM]
     │ 카운트 동그라미 +1 (또는 99+ 캡)
     │
     │ (병렬) AlarmPopup.show(data) ← alarm-ws.js 등이 별도 호출 → 팝업 표시
     │ → _DedupStore.add(key) 추가 (60s TTL)
```

### 2.3 60s 클라 dedup (alarm-popup.js show 흐름)

```
[AlarmPopup.show(data)]
     │
     ├─ data.event_resolved_at? → _handleResolved (변경 없음)
     │
     │ level = data.alarm_level
     │ if (level !== 'danger' && level !== 'warning') return
     │
     ├─ _AckStore.has(eventId)? → return  (Phase 1 user-scoped ack)
     │
     ├─ _DedupStore.has(dedupKey)? → return  ★ 신규 60s 클라 dedup
     │    │
     │    │ _DedupStore.has 안:
     │    │   map = _load()  ← localStorage 에서 fresh 항목 hydrate
     │    │   ts = map.get(key)
     │    │   if (ts && (now - ts) < TTL) return true  ← 60s 안 → skip
     │    │   if (ts && (now - ts) >= TTL) {
     │    │     map.delete(key); _persist();
     │    │     return false  ← TTL 만료 → stale 정리 후 통과
     │    │   }
     │    │   return false
     │
     │ _DedupStore.add(dedupKey)  ← 첫 도착 시 TTL 시작
     │
     ├─ admin path? → AlarmToastStack.push(data); return  (Phase 2 토스트)
     │
     │ ... (모달 표시 흐름 — 변경 없음)
```

#### dedup 키 (`_popupDedupKey`)
```js
function _popupDedupKey(data) {
  const eventId = data.event_id || data.id;
  if (eventId != null) return `event:${eventId}`;
  return `${data.alarm_type || 'unknown'}:${data.sensor_name || data.source_label || ''}:${data.alarm_level || ''}`;
}
```
- event-panel.js 의 `_dedupKey` 와 같은 컨벤션 (event_id 우선, 합성 fallback)
- 같은 event 의 백엔드 재푸시 → 같은 키 → 60s 안 skip
- event_id 없는 알람 (정상화 등) → 합성 키 (alarm_type + source + level)

### 2.4 DANGER 토스트 60s 무응답 → 모달 격상

```
[AlarmPopup.show(data) — admin_panel 경로]
     │ AlarmToastStack.push(data)
     ▼
[AlarmToastStack.push]
     │ container = _ensureContainer()  ← #alarm-toast-stack DOM 생성
     │ item = _createItem(data, level)  ← <div class="alarm-toast-stack-item danger">
     │ container.appendChild(item)
     │ if (eventId) _items.set(eventId, item)
     │
     │ ▶ 신규 분기 (2026-05-17 race fix) ◀
     │ item._timers = {}
     ├─ if (level === 'danger') {
     │    item._timers.escalate = setTimeout(() => {
     │      this._dismiss(eventId, item)  ← 토스트 사라짐
     │      AlarmPopup.show({...data, __forceModal: true})  ← 모달 재진입
     │    }, _TOAST_ESCALATE_MS)  ← 60_000
     │ }
     └─ else {  // warning
          item._timers.dismiss = setTimeout(() => _dismiss(...), 10_000)
        }

[운영자가 60s 안 토스트 클릭 시]
     │ item.addEventListener('click') 핸들러:
     │ clearTimeout(item._timers.dismiss)
     │ clearTimeout(item._timers.escalate)
     │ _dismiss(eventId, item) + AlarmPopup.show({...data, __forceModal: true})
     │ ↑ 즉시 격상 (사용자가 봤다는 명시)

[운영자가 60s 안 X 버튼 클릭 시]
     │ closeBtn.addEventListener('click'):
     │ _dismiss(eventId, item)  ← escalate 도 clearTimeout (사용자 명시 닫음)

[운영자 무응답 60s 경과]
     │ _timers.escalate fire
     │ _dismiss(eventId, item)  ← 토스트 사라짐
     │ AlarmPopup.show({...data, __forceModal: true})
     │ ↑ __forceModal 플래그 → _resolveDisplayMode() 가 toast 반환해도 모달 강제 진입
```

#### race fix 세부 (디버깅 학습 사례)
```
[기존 버그 흐름 (10s → 60s 변경 후)]
     │ DANGER 토스트:
     │   _timers.dismiss = setTimeout(15_000)     ← _TOAST_TTL_MS.danger
     │   _timers.escalate = setTimeout(60_000)    ← _TOAST_ESCALATE_MS
     │
     │ 15s 시점 → dismiss fire
     │   _dismiss(eventId, item) 호출
     │     clearTimeout(item._timers.escalate)  ← escalate cancel
     │     토스트 사라짐
     │
     │ 60s 시점 → escalate 이미 cancel — fire 안 됨
     │ ▶ 격상 안 됨 (사용자 보고)

[수정 후 흐름]
     │ DANGER 는 escalate timer 만 set
     │ WARNING 은 dismiss timer 만 set
     │ → DANGER 의 dismiss/escalate race 자체 없음
```

### 2.5 배지 클릭 → 이력 페이지 + reset

```
[운영자가 헤더 종 클릭]
     │
     ▼
[AlarmBadge._onBadgeClick]
     │ _count = 0
     │ _render()  ← 카운트 동그라미 hidden
     │ window.location.href = '/dashboard/monitoring/events/'
     ▼
[이력 페이지 진입]
     │ DOMContentLoaded → AlarmBadge.init()
     │ _fetchInitial() 재호출 → 진짜 user_unread_event_count 재산정
     │ ↑ 사이 본인이 ack 한 event 있으면 ↓
```

---

## 3. 핵심 함수 / 메서드 list

### 3.1 Backend

| 메서드 | 위치 | 역할 | 호출자 |
|---|---|---|---|
| `get_user_unread_event_count(user_id)` | `selectors/event_ack_selector.py:43` | NOT EXISTS subquery 로 본인 ack 안 한 active event count | `AlarmRecordViewSet.summary` |
| `AlarmRecordViewSet.summary` | `views/alarm_record.py:278` | 24h 누적 + 미확인 + **user_unread_event_count** 응답 | `GET /alerts/api/alarms/summary/` |

### 3.2 Frontend — alarm-badge.js (신규)

| 함수 | 역할 | 의존성 |
|---|---|---|
| `_resolveEls()` | `#btnAlarmBadge` + `.alarm-badge-count` 캐시. 헤더 없으면 false 반환 (silent skip 가드) | DOM |
| `_render()` | `_count` 상태 → DOM. 종 항상 표시 / 카운트 동그라미만 분기 + 99+ 캡 | `_btnEl`, `_countEl` |
| `_fetchInitial()` async | summary API fetch + `Math.max(_count, n)` race 보정 | `Auth.apiFetch` |
| `_onNewAlarm(ev)` | newAlarmEvent listener — `_count += 1` + `_render()` | — |
| `_onBadgeClick()` | reset + `window.location.href` 이동 | — |
| `init()` | 헤더 element 확보 + listener 등록 + fetch | 위 함수들 |
| `setCount(n)` / `getCount()` | 외부 호출용 (디버깅·테스트) | — |

### 3.3 Frontend — alarm-popup.js (신규/변경)

| 함수 / 변수 | 위치 | 역할 |
|---|---|---|
| `_DEDUP_STORE_KEY` / `_DEDUP_TTL_MS` | alarm-popup.js:79 | localStorage 키 / 60s TTL 상수 |
| `_DedupStore._load()` | alarm-popup.js:84 | localStorage 에서 hydrate + stale 자동 정리 |
| `_DedupStore.has(key)` | alarm-popup.js:99 | TTL 안이면 true, 만료 시 stale 정리 후 false |
| `_DedupStore.add(key)` | alarm-popup.js:111 | 신규 key + 현재 ts |
| `_DedupStore._persist()` | alarm-popup.js:117 | localStorage 영속화 — silent fail |
| `_popupDedupKey(data)` | alarm-popup.js:127 | event_id 우선, 합성 fallback (event-panel.js 컨벤션) |
| `AlarmPopup.show()` 의 dedup 분기 | alarm-popup.js:295 | `_DedupStore.has → return` + `_DedupStore.add` |
| `_TOAST_ESCALATE_MS` | alarm-popup.js:145 | **60_000** (이전 10_000 → 60_000) |
| `AlarmToastStack.push()` 의 timer 분기 | alarm-popup.js:172 | DANGER → escalate timer 만, WARNING → dismiss timer 만 (race fix) |

---

## 4. 재활용 자산 (본 작업의 핵심)

본 작업이 학습 시연 가치가 있는 이유 — **신규 라인 ~75줄 / 재활용 패턴 다수**. 사용자 메모리 [`code-reuse-preference`](/home/cjy/.claude/projects/-home-cjy-diconai/memory/code_reuse_preference.md) 원칙 충실.

### 4.1 `_AckStore` / `_LastSeen` → `_DedupStore`
```js
// 기존 _AckStore (Phase 1, 2026-05-15)
const _AckStore = {
  _map: null,
  _load() { /* localStorage read + TTL filter + Map hydrate */ },
  has(eventId) { /* ... */ },
  add(eventId) { /* ... */ },
  _persist() { /* localStorage write + silent fail */ },
};

// 신규 _DedupStore (본 작업) — 같은 구조 + TTL 60s + stale 자동 정리
const _DedupStore = {
  _map: null,
  _load() { /* 같은 패턴, 60s 필터 */ },
  has(key) { /* TTL 만료 시 stale delete + persist */ },
  add(key) { /* 같은 패턴 */ },
  _persist() { /* 같은 패턴 */ },
};
```

### 4.2 `get_acked_user_ids` → `get_user_unread_event_count`
```python
# 기존 (Phase 1) — 특정 event 의 ack 한 user set
def get_acked_user_ids(event_id: int) -> set[int]:
    return set(
        EventAcknowledgement.objects.filter(event_id=event_id)
            .values_list("user_id", flat=True)
    )

# 신규 — 반대 방향: 특정 user 가 ack 안 한 event count
def get_user_unread_event_count(user_id: int) -> int:
    return (
        Event.objects.filter(status__in=[ACTIVE, ACKNOWLEDGED, IN_PROGRESS])
        .exclude(event_acknowledgements__user_id=user_id)  # NOT EXISTS subquery
        .count()
    )
```
같은 모듈 + 같은 모델 (Phase 1 EventAcknowledgement) + 같은 인덱스 활용.

### 4.3 `droppedCount` + `_renderDropBadge` → AlarmBadge `_count` + `_render`
```js
// 기존 alarm-popup.js — 큐 풀 누락 카운터
droppedCount: 0,
_renderDropBadge() {
  const el = document.getElementById('alarm-popup-drop-badge');
  if (this.droppedCount > 0) { el.style.display = ''; cntEl.textContent = this.droppedCount; }
  else { el.style.display = 'none'; }
},

// 신규 AlarmBadge — 같은 카운터/render 패턴
let _count = 0;
function _render() {
  if (_count <= 0) _countEl.hidden = true;
  else { _countEl.hidden = false; _countEl.textContent = _count > 99 ? '99+' : count; }
}
```

### 4.4 newAlarmEvent CustomEvent — 발행자/구독자 패턴
```
발행자 (기존):
- alarm-ws.js
- worker-ws.js
- alarm-popup.js (_runCatchUp)

구독자 (기존):
- event-panel.js

신규 구독자:
- alarm-badge.js (AlarmBadge._onNewAlarm)
```
모듈 간 느슨한 결합. AlarmBadge 가 alarm-ws/worker-ws 와 직접 의존 없음.

### 4.5 `.badge` 패턴 (header.css) → `.alarm-badge-count`
```css
/* 기존 .badge — 헤더 우측 아이콘 위 작은 카운트 (13x13 고정) */
.badge {
  position: absolute; top: -4px; right: -6px;
  background: var(--danger); color: #fff;
  ...
}

/* 신규 .alarm-badge-count — 같은 absolute 패턴 + 적응형 너비 (1~3자리 수용) */
.alarm-badge-count {
  position: absolute; top: -2px; right: -2px;
  background: var(--danger); color: #fff;
  min-width: 14px; height: 14px;
  padding: 0 4px; border-radius: 7px;
  ...
}
```

### 4.6 `header.css` (다크) ↔ `admin.css` (라이트) 스크롤바 패턴
```css
/* 사이트 전체 스크롤바 (이전 commit 56b0c1b) — 같은 클래스, 색만 분리 */
/* header.css */  ::-webkit-scrollbar-thumb { background: var(--border); }
/* admin.css */   ::-webkit-scrollbar-thumb { background: #cbd5e1; }

/* 알람 배지도 같은 패턴 */
/* header.css */  .alarm-badge-count { background: var(--danger); }
/* admin.css */   .alarm-badge-count { background: #ef4444; }
```
다크/라이트 두 디자인 시스템 분리 — 색만 별도, 클래스/구조 동일.

---

## 5. 코드리뷰 관점

### 5.1 잘 된 점

1. **재활용 우선 원칙 충실** — 위 6개 패턴 모두 기존 자산 활용. 신규 라인 ~75줄로 D 옵션 4 효과 (헤더 배지 + dedup + 격상 + race fix) 달성
2. **race fix 자체가 학습 시연 가치** — 의도 변경 (`_TOAST_ESCALATE_MS` 10s → 60s) 이 다른 의도 (`_dismiss` 의 cleanup) 와 충돌. 디버깅 → 수정 흐름이 학습 자료
3. **테마 분리 일관성** — 스크롤바 패턴 (이전 commit) 과 동일한 다크/라이트 분리 — 두 디자인 시스템 공존 패턴 확립
4. **silent skip 가드** — `AlarmBadge.init` 의 `_resolveEls() === false` 시 즉시 return. 로그인 페이지 등 헤더 없는 환경에서도 안전
5. **race 보정** — `_fetchInitial` 결과를 `Math.max(_count, n)` — 동시 진행 중인 dispatch 카운트 보존 (catch-up 의 newAlarmEvent 가 fetch 보다 먼저 fire 됐을 때 누락 방지)
6. **인터페이스 분리** — AlarmBadge 가 외부 호출용 `setCount` / `getCount` 노출 — WS 통한 server-pushed count 도입 시 hook 지점 명확

### 5.2 잠재 리스크

| 리스크 | 영향 | 대응 방향 |
|---|---|---|
| `_DedupStore` 의 60s TTL 이 백엔드 `ALARM_REPOPUP_COOLDOWN_SEC` 와 불일치 시 어색한 동작 | 클라가 백엔드 통과 알람을 skip 또는 그 반대 | 두 값을 같이 변경하는 컨벤션 — refactoring 문서 가이드 참조 |
| `_count` 가 페이지 새로고침마다 fetch — server 진실과 클라 누적 사이 차이 가능 | 페이지 새로고침 후 운영자가 받았던 알람이 ack 안 됐는데 카운트 ↓ | 명확한 분기 — fetch 결과 = 본인 ack 안 한 event 수. 운영자가 명시 ack 안 했으면 카운트 유지. 정상 동작 |
| Lucide `@latest` (별개 commit 의 영향) — D 옵션 코드 무관하지만 같은 PR 안 영향 가능 | 시연 직전 호환 깨질 가능성 | refactoring 문서 의 main.html 주석 참조 |
| `_TOAST_ESCALATE_MS = 60_000` 학습 시연용. 운영 배포 시 운영자 피드백 필요 | 60s 너무 길거나 짧다고 판단 시 변경 | env 변수화 검토 (현재 클라 상수 — 변경 빈도 ↓ 가정) |
| AlarmBadge 가 newAlarmEvent 무조건 +1 — dedup 안 함 | 다중 탭 사용 시 같은 알람이 각 탭에서 +1 → 카운트 부정확 가능 | server-pushed count + WS broadcast 도입 시 해결. 현재는 페이지 새로고침 시 fetch 로 일관성 회복 |

### 5.3 다음 작업자 가이드

1. **WS 통한 server-pushed unread count 도입 시**
   - 신규 WS 메시지 타입 (예: `type: "unread_count_update"`) 추가
   - `AlarmBadge.setCount(n)` 활용 — 외부 호출용 API 이미 노출됨
   - 현재 newAlarmEvent 구독은 +1 누적만 — 서버 진실로 set 으로 대체 가능 (이중 카운팅 회피)

2. **차단형 정책 "첫 발화 + 60s 후 1회 재발화" 명시 도입 시**
   - 현재 백엔드 cooldown(60s) + 클라 dedup(60s) 동기화로 자연 충족
   - 명시적 setTimeout 추가는 race 위험만 ↑ — 현재 흐름 유지 권장
   - 디자인 디테일 (재발화 시 시각 강조 등) 필요 시 별도 검토

3. **dedup 시간 변경 시**
   - `_DEDUP_TTL_MS = N_000` 변경
   - **`ALARM_REPOPUP_COOLDOWN_SEC` 도 같이 변경** — 두 값 일치 컨벤션
   - `_TOAST_ESCALATE_MS` 도 같이 검토 (시간 척도 일관성)

4. **race fix 사후 검토 시점**
   - `AlarmToastStack.push` 의 `item._timers` 분기 (DANGER vs WARNING) 가 핵심
   - DANGER 는 escalate timer 만 — dismiss timer 가 다시 추가되면 race 재발 가능 (15s vs 60s)
   - 변경 시 시뮬레이터로 60s 격상 확인 필수

5. **헤더 배지 디자인 변경 시**
   - `header.css` + `admin.css` 두 곳 동일 수정 (스크롤바 패턴과 같음)
   - 종 SVG 자체는 `header.html` / `admin_panel/base.html` 의 path attribute

---

## 6. 부록

### 6.1 localStorage 키 (D 옵션 추가분)

| 키 | TTL | 용도 |
|---|---|---|
| `diconai:alarm:acked_event_ids` | 24h | Phase 1 user-scoped ack 영구 차단 (기존) |
| `diconai:alarm:last_seen_ts` | (없음) | WS catch-up 의 since= 기준점 (기존) |
| **`diconai:alarm:popup:dedup`** | **60s** | **D 옵션 — 같은 알람 60s 안 팝업 skip (신규)** |

### 6.2 summary API 응답 schema (D 옵션 추가분)

```json
{
  "last_24h_total": 42,
  "last_24h_danger": 8,
  "last_24h_warning": 14,
  "unacknowledged_event_count": 5,    // 글로벌 (Event.status 기반)
  "user_unread_event_count": 3        // ★ 신규 — user-scoped (Phase 1 활용)
}
```

차이:
- `unacknowledged_event_count`: Event.status ∈ {active, acknowledged, in_progress} — 운영팀 전체 처리해야 할 사건 수
- `user_unread_event_count`: 본인이 ack 안 한 그 중 일부 — 헤더 배지 초기값

### 6.3 CustomEvent 발행자 / 구독자 (D 옵션 후 전체)

| 모듈 | 역할 |
|---|---|
| **발행** alarm-ws.js | sensors WS → newAlarmEvent (dispatch on document) |
| **발행** worker-ws.js | worker WS → newAlarmEvent (dispatch on document) |
| **발행** alarm-popup.js (`_runCatchUp`) | catch-up API 의 missed alarms → newAlarmEvent (dispatch on window) |
| **구독** event-panel.js | 이벤트 패널 prepend (기존) |
| **구독** event_list.js | 이력 페이지 갱신 (기존) |
| **구독 (신규)** alarm-badge.js | 헤더 카운터 +1 |

### 6.4 race fix — timer state 전이도

```
DANGER alarm 도착:
     │
     ▼
[AlarmToastStack.push]
     │ item._timers = { escalate: setTimeout(60_000) }
     │           ↑ dismiss 안 set (race fix 후)
     │
     ├─ (60s 안) 운영자 토스트 클릭
     │    │ clearTimeout(escalate)
     │    │ _dismiss(item) + AlarmPopup.show({__forceModal: true})
     │    ▼ 즉시 모달 (사용자 명시)
     │
     ├─ (60s 안) 운영자 X 버튼 클릭
     │    │ _dismiss(item) → clearTimeout(escalate)
     │    ▼ 토스트 사라짐 (사용자 닫음 의사)
     │
     └─ (60s 경과) escalate fire
          │ _dismiss(item) → 토스트 사라짐
          │ AlarmPopup.show({__forceModal: true})
          ▼ 차단형 모달 격상

WARNING alarm 도착:
     │
     ▼
[AlarmToastStack.push]
     │ item._timers = { dismiss: setTimeout(10_000) }
     │           ↑ escalate 안 set (격상 없음)
     │
     ├─ (10s 안) 운영자 클릭 → 즉시 모달 (사용자 명시)
     │
     └─ (10s 경과) dismiss fire → 토스트 사라짐
```

### 6.5 commit 통계
- 변경 파일: 10
- 추가 라인: 299
- 삭제 라인: 10
- 신규 파일: 1 (alarm-badge.js)
- 회귀 테스트: DRF 53/53
