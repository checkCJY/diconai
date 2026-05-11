# 03. 알람 파이프라인 (alarm-ws · alarm-popup · worker-ws)

## 1. 관련 파일 및 의존성

### 1.1 파일 목록
- [drf-server/static/js/shared/alarm-ws.js](../../../drf-server/static/js/shared/alarm-ws.js) — 35줄, **비대시보드 페이지 알람 수신 IIFE**
- [drf-server/static/js/shared/worker-ws.js](../../../drf-server/static/js/shared/worker-ws.js) — 30줄, **작업자 개인 알림 IIFE**
- [drf-server/static/js/shared/alarm-popup.js](../../../drf-server/static/js/shared/alarm-popup.js) — 172줄, **`AlarmPopup` + `AlarmToast` 객체** (총 11개 메서드 + 모듈 상수 `_POPUP_CFG`)
- [drf-server/templates/components/alarm_popup.html](../../../drf-server/templates/components/alarm_popup.html) — 팝업·토스트 DOM (이 파일은 템플릿이라 함수 분석 대상 아님)
- 의존: [02 WSClient](02_ws_infrastructure.md), [01 Auth](01_auth_session.md), 백엔드 fastapi `/ws/sensors/`, `/ws/worker/{id}/`

### 1.2 호출자 인벤토리 (grep)
- **`AlarmPopup.show`**: alarm-ws.js:26, worker-ws.js:25, dashboard/websocket.js:420
- **`AlarmToast.show`**: alarm-ws.js:30, dashboard/websocket.js:422
- **`AlarmPopup.init`**: alarm-popup.js:131 (DOMContentLoaded 자동), dashboard/app.js:20 (명시 호출)
- **`AlarmToast.init`**: alarm-popup.js:132 (DOMContentLoaded 자동), dashboard/app.js:21 (명시 호출)
- **`document.dispatchEvent('newAlarmEvent')`** 송신: alarm-ws.js:28, worker-ws.js:26
- **`document.addEventListener('newAlarmEvent', ...)`** 수신: [detail/event_list.js:78](../../../drf-server/static/js/detail/event_list.js#L78) (다음 sprint 09에서 분석)

> **중요**: `init`이 두 곳에서 호출됨 — `_inited` 가드로 idempotent 보장 (정상). 그러나 명시 호출(dashboard/app.js)이 필요한 이유는 DOMContentLoaded보다 먼저 알람이 도착할 가능성 대비? 또는 history.

### 1.3 의존성 그래프
```
백엔드 fastapi /ws/sensors/ broadcast {alarms: [...]}
    │
    ├──▶ alarm-ws.js (비대시보드 페이지)
    │       │ key 변환
    │       ▼
    │       AlarmPopup.show(alarmData)
    │       └─ if risk_level==='normal' → AlarmToast.show
    │       └─ document.dispatchEvent('newAlarmEvent')
    │
    └──▶ dashboard/websocket.js (대시보드 메인)
            └─ AlarmPopup.show / AlarmToast.show (동일 패턴)

백엔드 fastapi /ws/worker/{user_id}/ {type:'worker_alert', ...}
    │
    └──▶ worker-ws.js (개인 작업자 단말)
            └─ AlarmPopup.show + dispatchEvent('newAlarmEvent')
```

### 1.4 contract 정합성 hotspot

서버 → 클라이언트 메시지 키 변환:
| 서버 키 (백엔드 alarm payload) | alarm-ws.js 변환 | worker-ws.js 변환 | dashboard/websocket.js 변환 | AlarmPopup.show 사용 |
|---|---|---|---|---|
| `risk_level` | `alarm_level` | `alarm_level` | `alarm_level` | `data.alarm_level` |
| `is_new_event` | `is_new_event` (그대로) | `is_new_event` | `is_new_event` | `data.is_new_event` (실제 분기는 호출자에서) |
| `summary` | `message` | `message` | `message` | `data.message \|\| data.summary` (양쪽 fallback!) |
| `source_label` | `sensor_name` | `source_label` | `sensor_name` | `data.sensor_name \|\| data.source_label` |
| `event_id` | `event_id` | `event_id` | `event_id` | `data.event_id \|\| data.id` |
| `gas_type` | `gas_type` | (생략) | `gas_type` | (alarm-ws만 포함) |

> ❌ **이 contract 변환이 알람 도메인의 가장 큰 fragility**. 같은 데이터를 3개 호출자가 각자 변환 + AlarmPopup이 양쪽 fallback. 백엔드 키 변경 시 한 호출자라도 누락하면 silent 실패.

## 2. 기능 흐름

### 2.1 비대시보드 페이지에서 위험/주의 알람 도착
```
fastapi /ws/sensors/ tick (alarm_flush_loop)
  payload = { alarms: [{risk_level, is_new_event, summary, source_label, gas_type, event_id, ...}] }
    │
    ▼ (브라우저)
WSClient → 같은 page의 alarm-ws.js + (있다면 dashboard/websocket.js) 동시 dispatch
    │
alarm-ws.js onMessage:
    ├─ data.alarms 배열 체크 (없으면 return)
    ├─ for each alarm:
    │   ├─ alarmData = { alarm_level: alarm.risk_level, message: alarm.summary, ... }
    │   ├─ if alarm.is_new_event → AlarmPopup.show(alarmData)
    │   ├─ document.dispatchEvent('newAlarmEvent', detail=alarmData)
    │   └─ if alarm.risk_level==='normal' && AlarmToast → AlarmToast.show
    │
AlarmPopup.show:
    ├─ level !== 'danger' && !== 'warning' → return (정상 알람은 팝업 안 뜸)
    ├─ queue.length >= 5 → return (silent drop)
    ├─ queue.push(alarmData)
    └─ if !isOpen → _process()
        ├─ queue.shift()
        ├─ DOM 업데이트 (popup, time, icon, type, action, level, message)
        ├─ popup.display = 'block'
        └─ setTimeout(close, 10000ms)
```

### 2.2 작업자 개인 알림 (지오펜스 진입)
```
백엔드 alarm_router /internal/alarms/push/
  alarm_type='geofence_intrusion' + worker_id=N
    │
    ├─ active_alarms 추가 (sensor_clients 전체 broadcast로도 감)
    └─ if worker_id → worker_clients[N].send_json({type:'worker_alert', risk_level, summary, ...})

브라우저 (해당 user의 단말):
worker-ws.js IIFE 시작:
    ├─ DOMContentLoaded → Auth.getMe() (api 호출, 토큰 의존)
    ├─ user.id 없으면 return
    ├─ WSClient.connect('/ws/worker/' + user.id + '/')
    ├─ ws.onMessage:
    │   ├─ data.type !== 'worker_alert' → return
    │   ├─ alarmData = { alarm_level: data.risk_level, message: data.summary, ... }
    │   └─ AlarmPopup.show(alarmData) + dispatchEvent('newAlarmEvent')
```

### 2.3 알람 큐 처리 (3개 알람 연속 도착 시나리오)
```
T=0초: 알람 A (danger) 도착
  AlarmPopup.show(A):
    queue.length(0) < 5 → push A → queue=[A]
    !isOpen → _process()
      queue.shift() → queue=[], data=A
      isOpen=true, popup 노출
      setTimeout(close, 10000)

T=2초: 알람 B (warning) 도착
  AlarmPopup.show(B):
    queue.length(0) < 5 → push B → queue=[B]
    isOpen=true → _process 호출 안 함 (current popup 유지)

T=10초: A 자동 close
  close() → popup hidden, isOpen=false → _process()
    queue.shift() → queue=[], data=B
    isOpen=true, popup 노출

T=12초: 알람 C, D, E, F, G (5개) 동시 도착
  C: queue=[C], length 1 < 5 → push
  D: queue=[C,D], length 2 < 5 → push
  E: queue=[C,D,E], length 3 < 5 → push
  F: queue=[C,D,E,F], length 4 < 5 → push
  G: queue=[C,D,E,F,G], length 5 >= 5 → ❌ silent drop!
```

> **중요한 동작**: queue 5개 가득 차면 6번째부터 **silent drop**. B가 popup 표시 중이라 queue에 들어간 C~G 중 G만 drop. UI상으로 사용자는 5개 알람을 순차로 보지만 G의 누락은 모름.

## 3. 함수 분석

### 3.1 [shared/alarm-ws.js](../../../drf-server/static/js/shared/alarm-ws.js) — IIFE

#### 모듈 IIFE
- **시그니처**: 즉시 실행 IIFE
- **역할**: DOMContentLoaded 시 `/ws/sensors/` 연결 + 알람 처리 등록
- **단계별 동작**:
  1. `document.addEventListener('DOMContentLoaded', function() {...})` (alarm-ws.js:9)
  2. `const ws = WSClient.connect('/ws/sensors/');` (alarm-ws.js:10)
  3. `ws.onMessage(function(data) {...})` 핸들러 등록 (alarm-ws.js:12)
  4. 핸들러 내부:
     - `if (!Array.isArray(data.alarms) || data.alarms.length === 0) return;` (alarm-ws.js:13)
     - `data.alarms.forEach(function(alarm) { ... })` (alarm-ws.js:15)
- **호출하는 함수**: `WSClient.connect`, `Array.isArray`, `Array.prototype.forEach`
- **호출자**: 페이지 자동 로드
- **올바름 검증**:
  - ✅ DOMContentLoaded 가드 — DOM 준비 후 실행 보장.
  - ✅ Array.isArray + length 0 가드 — 잘못된 페이로드 방어.
  - ⚠️ **WSClient.connect 결과를 unsubscribe 안 함** — 페이지 언마운트 시 핸들러 누수. SPA가 아닌 multi-page 라 페이지 navigation 시 자동 정리 — 영향 미미.
  - 💡 비대시보드 페이지에서 작동을 의도하는데, 현재는 **모든 페이지에 로드되면 동작** — 대시보드 페이지에 alarm-ws.js와 dashboard/websocket.js가 둘 다 로드되면 같은 알람을 두 번 처리할 가능성. WSClient 캐시로 연결은 1개지만 **두 개의 onMessage 핸들러** → 둘 다 `AlarmPopup.show` 호출 → queue.push 두 번. 중복 처리 위험.

#### `forEach` 콜백 (alarm-ws.js:15-32)
- **시그니처**: `(alarm: ServerAlarm) => void`
- **역할**: 한 알람을 클라이언트 형식으로 변환 + 팝업/토스트/이벤트 dispatch
- **단계별 동작**:
  1. `alarmData = {...}` 객체 생성 — 6개 필드 매핑 (alarm-ws.js:16-23):
     - `alarm_level: alarm.risk_level`
     - `is_new_event: alarm.is_new_event`
     - `message: alarm.summary`
     - `sensor_name: alarm.source_label`
     - `timestamp: new Date().toISOString()` ← 클라이언트 시각
     - `gas_type: alarm.gas_type`
     - `event_id: alarm.event_id`
  2. `if (alarm.is_new_event) AlarmPopup.show(alarmData);` (alarm-ws.js:25-27)
  3. `document.dispatchEvent(new CustomEvent('newAlarmEvent', { detail: alarmData }));` (alarm-ws.js:28)
  4. `if (alarm.risk_level === 'normal' && typeof AlarmToast !== 'undefined') AlarmToast.show(alarmData);` (alarm-ws.js:29-31)
- **호출하는 함수**: `AlarmPopup.show`, `AlarmToast.show`, `document.dispatchEvent`, `CustomEvent`, `Date#toISOString`
- **호출자**: ws.onMessage가 dispatch 시 (페이로드당 1회)
- **올바름 검증**:
  - ❌ **`timestamp: new Date().toISOString()` — 클라이언트 시각**. 서버가 보낸 알람 시각이 아닌 메시지 수신 시각. broadcast가 늦으면 사용자는 "지금 발생"이라 인식. 백엔드 alarm payload에 `created_at` 등이 있으면 그걸 사용해야 정확.
  - ❌ **`is_new_event=true`만 팝업, `risk_level==='normal'`만 토스트 — 두 분기 사이 누락 가능**. `is_new_event=false` + risk_level=`'warning'`/`'danger'` 알람은 팝업도 토스트도 안 뜸. 정상 시나리오에선 발생 안 하나, 백엔드 변경 시 silent 누락.
  - ⚠️ **`typeof AlarmToast !== 'undefined'` 가드** — alarm-popup.js가 페이지에 로드 안 됐을 때 silent skip. 의도이지만 디버깅 어려움 — 누가 토스트 누락을 보고하면 원인 추적 시간 듦.
  - ⚠️ **dispatchEvent('newAlarmEvent')는 모든 알람에 발사** — `is_new_event` 분기 없이. event_list.js가 매번 새로고침하면 부하. (다음 sprint에서 검증 필요)
  - 💡 **키 매핑 인라인** — 한 곳에서만 사용되지만, worker-ws.js의 동일 패턴과 중복.

### 3.2 [shared/worker-ws.js](../../../drf-server/static/js/shared/worker-ws.js) — IIFE

#### 모듈 IIFE
- **시그니처**: 즉시 실행 IIFE
- **역할**: 작업자 로그인 시 본인 user_id로 `/ws/worker/{id}/` 연결 + 개인 알람 처리
- **단계별 동작**:
  1. `document.addEventListener('DOMContentLoaded', async function() { ... })` (worker-ws.js:7)
  2. `const user = await Auth.getMe();` (worker-ws.js:8) — JWT 인증 확인
  3. `if (!user || !user.id) return;` (worker-ws.js:9) — 미로그인 또는 응답 형식 이상
  4. `const ws = WSClient.connect('/ws/worker/' + user.id + '/');` (worker-ws.js:11)
  5. `ws.onMessage(function(data) { ... })` 핸들러 (worker-ws.js:13)
  6. 핸들러 내부:
     - `if (data.type !== 'worker_alert') return;` (worker-ws.js:14)
     - `alarmData = {...}` 매핑 (worker-ws.js:16-23)
     - `if (typeof AlarmPopup !== 'undefined') { AlarmPopup.show(alarmData); document.dispatchEvent('newAlarmEvent') }` (worker-ws.js:24-27)
- **호출하는 함수**: `Auth.getMe`, `WSClient.connect`, `AlarmPopup.show`, `document.dispatchEvent`
- **호출자**: 페이지 자동 로드 (worker-ws.js가 로드된 페이지)
- **올바름 검증**:
  - ❌ **클라이언트가 user_id 결정** (이전 리뷰 04 D2 / 07 G1) — 서버가 검증 안 하면 임의 ID 접속 가능. 이미 식별된 핵심 보안 이슈.
  - ❌ **AlarmToast 분기 없음** — alarm-ws.js와 달리 worker-ws.js는 토스트 호출 안 함. 일관성 결여 — 의도인지 누락인지 명확하지 않음.
  - ⚠️ **`Auth.getMe()` 실패 시 silent return** — 사용자에게 "알림 받기 실패" 표시 없음. 작업자가 위험 영역 진입 알림을 못 받는 사고 가능. 명시적 에러 표시 필요.
  - ⚠️ **WS 인증이 attachToken 옵션 없이 connect** — 토큰 query 부착 안 됨. 서버 측 인증 도입 시 즉시 깨짐 → 모든 worker-ws 연결 실패.
  - 💡 `data.type` 외 다른 type 메시지를 무시 — 미래 확장 시 타입 분기 추가 가능.
  - 💡 alarm-ws.js와 거의 동일한 키 매핑 코드 — 추출 가능 (R1).

### 3.3 [shared/alarm-popup.js](../../../drf-server/static/js/shared/alarm-popup.js) — `AlarmPopup` 객체

#### 모듈 상수 `_POPUP_CFG` (alarm-popup.js:9-28)
- **타입**: `{[level: 'danger'|'warning']: PopupConfig}`
- **역할**: level별 borderColor·iconClass·typeLabel·actionText·badge 설정
- **올바름 검증**:
  - ✅ 명확한 설정 분리. `'danger'`/`'warning'` 두 키만 — `'normal'` 등은 처리 안 함 (정상은 토스트가 처리).
  - ⚠️ **`iconClass: ''` (danger) vs `'caution'` (warning)** — danger의 빈 문자열은 의도? 추가 클래스 적용 안 함. CSS에서 `.alarm-popup-icon`으로 스타일 처리 가정.
  - 💡 객체가 frozen/Object.freeze 아님 — 외부에서 수정 가능. 모듈 상수면 freeze 권장 (사소).

#### `AlarmPopup.show(data)` (alarm-popup.js:40-47)
- **시그니처**: `(data: AlarmData) => void`
- **역할**: 알람 데이터를 큐에 추가 + 처리 시작
- **단계별 동작**:
  1. `const level = data.alarm_level;` (40)
  2. `if (level !== 'danger' && level !== 'warning') return;` (41) — normal/기타 무시
  3. `if (this.queue.length >= this.MAX_QUEUE) return;` (44) — **5개 가득 시 silent drop**
  4. `this.queue.push(data);` (45)
  5. `if (!this.isOpen) this._process();` (46)
- **호출자**: alarm-ws.js, worker-ws.js, dashboard/websocket.js
- **올바름 검증**:
  - ❌ **MAX_QUEUE=5 silent drop** (이전 리뷰 03·04 재확인) — 5개 가득 시 드랍. 산재 예방 시스템에서 알람 누락은 직접 사고 가능. 운영팀에 노출 안 됨.
  - ⚠️ **level 검증 후 push — 검증 외 분기 누락**. level이 `null`/`undefined`이면 두 분기 모두 false → 무시. 그러나 백엔드 contract 위반 시 silent.
  - ⚠️ **`isOpen` 동시성** — JS는 단일 스레드라 race 없으나, queue 길이 검사와 push 사이 비동기 yield 없으니 안전.
  - 💡 `MAX_QUEUE=5` 매직넘버 — 상단에 const로 노출돼 있어 조정 가능.

#### `AlarmPopup._process()` (alarm-popup.js:49-96)
- **시그니처**: `() => void`
- **역할**: 큐에서 다음 알람을 꺼내 DOM 업데이트 + 노출 + 자동 닫기 타이머
- **단계별 동작**:
  1. `if (this.queue.length === 0) { this.isOpen = false; return; }` (50)
  2. `this.isOpen = true;` (51)
  3. `const data = this.queue.shift();` (52)
  4. `const cfg = _POPUP_CFG[data.alarm_level] || _POPUP_CFG.danger;` (53) — fallback to danger
  5. `this._currentId = data.event_id || data.id || null;` (54) — 상세 페이지 이동용
  6. `const popup = document.getElementById('alarm-popup'); if (!popup) { this.isOpen = false; return; }` (56-57) — DOM 부재 가드
  7. `popup.style.borderLeftColor = cfg.borderColor;` (59)
  8. **timeEl** 업데이트 (61-67):
     - `data.timestamp || data.created_at`을 `new Date(...).toLocaleString('ko-KR', {hour12:false})` 또는 `'--'`
  9. **iconEl** 업데이트 (69-70): `className = 'alarm-popup-icon ' + cfg.iconClass`
  10. **typeEl** 업데이트 (72-73): `cfg.typeLabel`
  11. **actionEl** 업데이트 (75-79): textContent + className
  12. **levelEl** (배지) 업데이트 (81-85): textContent + className
  13. **msgEl** 업데이트 (87-92):
      - `sensor = data.sensor_name || data.source_label || ''`
      - `msg = data.message || data.summary || ''`
      - `msgEl.textContent = sensor ? sensor + ' — ' + msg : msg`
  14. `popup.style.display = 'block';` (94)
  15. `this._autoCloseTimer = setTimeout(() => this.close(), 10000);` (95) — 10초 자동 닫기
- **호출하는 함수**: `Array.shift`, `document.getElementById`, `Date`, `Date#toLocaleString`, `setTimeout`
- **호출자**: `show` (큐 첫 push 시), `close` (큐가 더 있을 때)
- **올바름 검증**:
  - ✅ 모든 DOM 참조에 `if (xxxEl)` 가드 — 부분 DOM 부재에 안전.
  - ✅ **`_POPUP_CFG[level] || _POPUP_CFG.danger` fallback** — 잘못된 level이 들어와도 화면은 표시 (안전).
  - ❌ **`textContent` 사용 — XSS 안전 ✅** (innerHTML 안 씀).
  - ❌ **양쪽 키 fallback** (`sensor_name || source_label`, `message || summary`) — 클라이언트 코드가 양쪽 contract 모두 지원. **호출자에서 변환 안 해도 됨** — 그럼 alarm-ws/worker-ws의 변환은 왜 하나? 중복 안전장치. **fragility 핵심**.
  - ⚠️ **`data.timestamp` vs `data.created_at` fallback** — alarm-ws는 `timestamp` 부착, worker-ws도 `timestamp` 부착, dashboard/websocket.js는? 백엔드 원시 페이로드는 `created_at` 가능. 둘 다 지원 — OK이지만 contract 모호.
  - ⚠️ **`new Date(ts).toLocaleString('ko-KR', {hour12: false})`** — ts가 잘못된 형식이면 `Invalid Date` 출력. 검증 부재.
  - ⚠️ **`_autoCloseTimer`가 인스턴스 변수가 아닌 동적 속성** — `_process` 호출마다 새 timer 할당. 이전 timer는 close()가 처리. 그러나 `show` 다음 `show` 다음 `_process`가 빠르게 일어나면 마지막 timer만 살아 있음 (정상 — _process는 close 후에만 호출되니).
  - 💡 14단계의 DOM 업데이트가 직렬 — 한 번 reflow 강제. `requestAnimationFrame` 또는 `display='block'` 마지막에 두기로 최적화 가능 (사소).
  - 💡 자동 close 시간 10초 매직넘버.

#### `AlarmPopup.close()` (alarm-popup.js:98-105)
- **시그니처**: `() => void`
- **역할**: 현재 팝업 닫기 + 다음 큐 처리
- **단계별 동작**:
  1. `clearTimeout(this._autoCloseTimer);` (99)
  2. `this._currentId = null;` (100)
  3. `popup.display = 'none'` (101-102)
  4. `this.isOpen = false;` (103)
  5. `this._process();` (104) — 다음 알람 처리
- **호출자**: 자동 close (setTimeout), close 버튼 클릭, confirm 버튼 클릭
- **올바름 검증**:
  - ✅ clearTimeout으로 중복 close 방지. 단순 상태 정리.
  - 💡 `_currentId = null` — 닫힌 후 _goDetail 클릭 시 fallback URL로 이동. 의도된 동작.

#### `AlarmPopup._goDetail()` (alarm-popup.js:107-119)
- **시그니처**: `() => void`
- **역할**: 현재 알람의 상세 페이지로 이동 + **큐 전체 클리어**
- **단계별 동작**:
  1. `const id = this._currentId;` (108)
  2. `clearTimeout(this._autoCloseTimer);` (110)
  3. `this._currentId = null;` (111)
  4. `this.isOpen = false;` (112)
  5. `this.queue = [];` ❗ **큐 전체 비움** (113)
  6. popup hide (114-115)
  7. `window.location.href = id ? '/dashboard/monitoring/events/' + id + '/' : '/dashboard/monitoring/events/';` (116-118)
- **호출자**: '상세보기' 버튼 클릭 (init에서 바인딩)
- **올바름 검증**:
  - ❌ **`queue = []` — 의도된 동작인가?** (이전 리뷰 hotspot #12) 사용자가 첫 알람을 보다가 상세 클릭하면, 대기 중인 다른 4개 알람은 모두 사라짐. 페이지 이동 후 새로고침되니 큐가 의미 없는 건 사실이지만 — 새 페이지에선 알람이 새로 도착하지 않으면 누락.
  - 💡 **window.location.href로 SPA가 아닌 풀 페이지 이동** — 의도된 디자인이라면 OK. 큐 클리어는 합리적 (어차피 페이지 이동).
  - ⚠️ id 부재 시 `/dashboard/monitoring/events/`로 fallback — 목록 페이지로 이동. UX OK.

#### `AlarmPopup.init()` (alarm-popup.js:121-127)
- **시그니처**: `() => void`
- **역할**: 닫기/확인/상세 버튼 이벤트 바인딩 (idempotent)
- **단계별 동작**:
  1. `if (this._inited) return;` (122) — 중복 호출 방지
  2. `this._inited = true;` (123)
  3. close 버튼: `_inited` true 후 옵셔널 체이닝으로 바인딩 (124)
  4. confirm 버튼 → close (125)
  5. detail 버튼 → _goDetail (126)
- **호출자**: alarm-popup.js의 DOMContentLoaded(131), dashboard/app.js:20 (명시 호출)
- **올바름 검증**:
  - ✅ `_inited` 가드 — 두 곳 호출에 안전.
  - ✅ `?.addEventListener` — DOM 부재 안전.
  - 💡 명시 호출 필요성 의문 — DOMContentLoaded면 충분. dashboard/app.js의 명시 호출은 leftover 가능성. 코드 검토 시 단순화 가능.

#### DOMContentLoaded 자동 init (alarm-popup.js:130-133)
- **역할**: AlarmPopup.init + AlarmToast.init 자동 호출
- **올바름 검증**:
  - ✅ 정상.

### 3.4 [shared/alarm-popup.js](../../../drf-server/static/js/shared/alarm-popup.js) — `AlarmToast` 객체 (alarm-popup.js:138-171)

#### `AlarmToast.show(data)` (alarm-popup.js:142-158)
- **시그니처**: `(data: AlarmData) => void`
- **역할**: 정상화 토스트 (우하단 비차단형) 5초 노출
- **단계별 동작**:
  1. `const toast = document.getElementById('alarm-toast'); if (!toast) return;` (143-144)
  2. `clearTimeout(this._timer);` (146) — 이전 토스트 타이머 취소
  3. sensor/msg fallback (148-151)
  4. `msgEl.textContent = sensor ? sensor + ' — ' + msg : msg;` (151)
  5. **`toast.style.display = 'none'`** (153) — **재시작 트릭**
  6. `requestAnimationFrame(() => { toast.display='flex'; this._timer = setTimeout(close, 5000); })` (154-157)
- **호출자**: alarm-ws.js, dashboard/websocket.js
- **올바름 검증**:
  - ✅ **display='none' → rAF → display='flex' 트릭** — CSS 애니메이션 재시작 위해 의도된 패턴 (이전 리뷰 hotspot #13). reflow를 강제해 transition 다시 트리거. 정상.
  - ✅ clearTimeout으로 이전 토스트 타이머 정리.
  - ✅ DOM 부재 가드.
  - 💡 5초 매직넘버.
  - 💡 큐잉 안 함 — 빠른 연속 알람은 마지막 1개만 표시. 의도된 동작 (정상화 토스트는 비핵심 알람이라 OK).

#### `AlarmToast.close()` (alarm-popup.js:160-164)
- **시그니처**: `() => void`
- **역할**: 토스트 숨기기 + 타이머 정리
- **올바름 검증**: ✅ 정상.

#### `AlarmToast.init()` (alarm-popup.js:166-170)
- **시그니처**: `() => void`
- **역할**: 닫기 버튼 바인딩 (idempotent)
- **올바름 검증**: ✅ `_inited` 가드 OK.

## 4. 종합 평가

### 강점
- ✅ **두 알람 클래스의 명확한 책임 분리** — Popup(차단형, 위험·주의), Toast(비차단형, 정상화).
- ✅ **idempotent init** — `_inited` 가드로 중복 호출 안전.
- ✅ **textContent 사용** — XSS 안전.
- ✅ **DOM 부재 가드 (`if (popup)`)** — 페이지에 alarm_popup.html include 안 된 경우 안전.
- ✅ **큐 + isOpen 상태 관리** — 단순하지만 정확.
- ✅ **AlarmToast의 rAF reflow 트릭** — 알 만한 사람이 본 디테일.

### 약점
- ❌ **MAX_QUEUE=5 silent drop** — 가장 큰 이슈. 알람 누락은 산업 안전 시스템에서 치명적.
- ❌ **클라이언트 timestamp** — 서버 시각 무시. 사용자 시각 인식 부정확.
- ❌ **3곳 호출자의 키 변환 + AlarmPopup의 양쪽 fallback** — contract fragility 핵심.
- ⚠️ **AlarmToast 호출 비대칭** — alarm-ws.js와 dashboard/websocket.js만 호출, worker-ws는 안 함.
- ⚠️ **_goDetail이 큐 전체 클리어** — 의도일 수 있으나 명시 부족.

### 중복 / 누락
- 📌 **alarm-ws.js 키 매핑과 worker-ws.js 키 매핑이 거의 동일** — 추출 필요.
- 📌 **dashboard/websocket.js의 알람 처리도 비슷** (다음 sprint에서 검증).
- 📌 **`document.dispatchEvent('newAlarmEvent')` 송신은 2곳, 수신은 event_list.js만** — 명시적 EventBus 부재 (이전 리뷰 04 D10).

### contract 정합성
- ⚠️ **AlarmPopup.show의 fallback 패턴이 호출자의 변환을 사실상 불필요하게 만듦** — 호출자가 변환 안 해도 작동. 그러나 호출자가 변환을 한 채로 fallback 보유 — 이중 안전장치라 fragile하지 않지만 의도가 모호.

## 5. 리팩토링 권고

### R1. `shared/alarm-mapper.js` 추출 — 키 변환 단일화 [상 · 소]
- **왜 필요?**: alarm-ws.js (16-23), worker-ws.js (16-23), dashboard/websocket.js (~410-425)에 거의 동일한 매핑 코드. 백엔드 키 변경 시 3곳 모두 갱신 필요 — 한 곳 누락 시 silent break.
- **장점**: 단일 진실 원천 / 변경 1곳 / 단위 테스트 가능.
- **단점**: 새 파일 1개. 스크립트 로드 순서 관리.
- **변경 위치**: 신규 [shared/alarm-mapper.js](../../../drf-server/static/js/shared/) — alarm-ws.js, worker-ws.js, dashboard/websocket.js에서 import.
- **변경 예시**:
  ```js
  // shared/alarm-mapper.js
  'use strict';
  const AlarmMapper = {
    // 서버 sensors 알람 → 클라이언트 형식
    fromSensorsAlarm(serverAlarm) {
      return {
        alarm_level:  serverAlarm.risk_level,
        is_new_event: serverAlarm.is_new_event,
        message:      serverAlarm.summary,
        sensor_name:  serverAlarm.source_label,
        timestamp:    serverAlarm.created_at || new Date().toISOString(), // 서버 시각 우선
        gas_type:     serverAlarm.gas_type,
        event_id:     serverAlarm.event_id,
      };
    },
    // 서버 worker_alert → 클라이언트 형식
    fromWorkerAlert(serverData) {
      return {
        alarm_level:  serverData.risk_level,
        is_new_event: serverData.is_new_event,
        message:      serverData.summary,
        sensor_name:  serverData.source_label,
        timestamp:    serverData.created_at || new Date().toISOString(),
        event_id:     serverData.event_id,
      };
    },
  };
  // window.AlarmMapper = AlarmMapper; // 글로벌 노출
  ```
  ```js
  // alarm-ws.js (after)
  data.alarms.forEach(function (alarm) {
    const alarmData = AlarmMapper.fromSensorsAlarm(alarm);
    if (alarm.is_new_event) AlarmPopup.show(alarmData);
    document.dispatchEvent(new CustomEvent('newAlarmEvent', { detail: alarmData }));
    if (alarm.risk_level === 'normal' && typeof AlarmToast !== 'undefined') {
      AlarmToast.show(alarmData);
    }
  });
  ```
  ※ 더 좋은 옵션: **백엔드 키를 클라이언트 키와 통일** — 매퍼 자체를 제거. 그러나 백엔드 호환성 영향 큼 → 매퍼 도입이 현실적.

### R2. AlarmPopup 큐 정책 명시·재설계 [상 · 중]
- **왜 필요?**: silent drop은 산재 예방 시스템에서 직접적 사고 가능성. 운영팀에 통계 노출 부재.
- **장점**: 알람 누락 가시화 / 정책 합의 명시.
- **단점**: UX 정책 결정 필요 (drop vs throttle vs group).
- **변경 위치**: [alarm-popup.js:38, 40-47](../../../drf-server/static/js/shared/alarm-popup.js#L38-L47)
- **변경 예시 (3가지 옵션)**:
  ```js
  // 옵션 A: drop count + 통계 노출
  const AlarmPopup = {
    queue: [],
    droppedCount: 0,  // 신규
    MAX_QUEUE: 5,
    show(data) {
      if (this.queue.length >= this.MAX_QUEUE) {
        this.droppedCount++;
        console.warn('[AlarmPopup] queue full, dropping', { dropped: this.droppedCount });
        // 운영 도구로 전송 또는 UI에 "+N개 알람 누락" 배지
        return;
      }
      // ...
    },
  };

  // 옵션 B: same source_label 그룹핑 (시간대 5초 내)
  show(data) {
    const last = this.queue[this.queue.length - 1];
    if (last && last.sensor_name === data.sensor_name &&
        (Date.now() - new Date(last.timestamp).getTime()) < 5000) {
      last.count = (last.count || 1) + 1;
      last.message = `${data.message} (×${last.count})`;
      return;
    }
    this.queue.push(data);
    // ...
  }

  // 옵션 C: 위험도 우선순위 큐 (danger 먼저 처리)
  show(data) {
    const insertIdx = data.alarm_level === 'danger'
      ? 0  // danger는 큐 맨 앞
      : this.queue.length;
    this.queue.splice(insertIdx, 0, data);
    // ...
  }
  ```
  ※ 운영팀과 합의 후 결정. 옵션 B가 가장 현실적 (실제 운영에서 같은 센서 연속 알람 빈발).

### R3. 서버 timestamp 사용 [중 · 소]
- **왜 필요?**: 클라이언트 시각은 broadcast 지연·시계 어긋남에 영향. 사고 시각 정확성 중요.
- **장점**: 정확한 시각 / 감사 트레일 일관.
- **단점**: 서버가 알람 페이로드에 timestamp(`created_at`) 일관 포함 보장 필요. 백엔드 변경 동반 가능.
- **변경 위치**: [alarm-ws.js:21](../../../drf-server/static/js/shared/alarm-ws.js#L21), [worker-ws.js:21](../../../drf-server/static/js/shared/worker-ws.js#L21), AlarmMapper (R1)
- **변경 예시**:
  ```js
  // alarm-mapper.js fromSensorsAlarm 내부
  timestamp: serverAlarm.created_at || serverAlarm.alarm_created_at || new Date().toISOString(),
  // fallback은 안전망, 정상 운영에선 서버 시각 사용
  ```

### R4. AlarmToast 호출 일관 [중 · 소]
- **왜 필요?**: alarm-ws는 normal 토스트 호출, worker-ws는 안 함. 일관성 부족 — worker_alert에 normal level이 안 와서 의도된 건지, 누락인지 불명.
- **장점**: 코드 의도 명확.
- **단점**: 정책 결정 필요.
- **변경 위치**: [worker-ws.js:24-27](../../../drf-server/static/js/shared/worker-ws.js#L24-L27)
- **변경 예시**:
  ```js
  // worker-ws.js (after)
  if (typeof AlarmPopup !== 'undefined') {
    AlarmPopup.show(alarmData);
    document.dispatchEvent(new CustomEvent('newAlarmEvent', { detail: alarmData }));
  }
  // 정상화 알람도 작업자에게 토스트로 알림
  if (alarmData.alarm_level === 'normal' && typeof AlarmToast !== 'undefined') {
    AlarmToast.show(alarmData);
  }
  ```
  ※ 또는 **명시적 정책 주석**: "worker_alert는 위험만 도달, 정상화 토스트 불필요" 명시.

### R5. EventBus 패턴 도입 [중 · 중]
- **왜 필요?**: `document.dispatchEvent('newAlarmEvent')` 암묵 통신. 누가 구독하는지 grep해야 알 수 있음. 향후 다른 도메인 이벤트 추가 시 namespace 충돌 위험.
- **장점**: 명시적 이벤트 정의 / 타입 추적 / namespace 격리.
- **단점**: 새 모듈 1개. 기존 dispatch 패턴 변경.
- **변경 위치**: 신규 [shared/event-bus.js](../../../drf-server/static/js/shared/)
- **변경 예시**:
  ```js
  // shared/event-bus.js
  'use strict';
  const EventBus = (function () {
    const handlers = new Map(); // event_name → Set<fn>
    return {
      on(event, fn) {
        if (!handlers.has(event)) handlers.set(event, new Set());
        handlers.get(event).add(fn);
        return () => handlers.get(event)?.delete(fn);
      },
      emit(event, payload) {
        handlers.get(event)?.forEach(fn => {
          try { fn(payload); } catch (e) { console.error('[EventBus]', event, e); }
        });
      },
      // 알려진 이벤트 명시
      events: {
        ALARM_NEW: 'alarm:new',
        ALARM_DETAIL: 'alarm:detail',
      },
    };
  })();
  ```
  ```js
  // alarm-ws.js (after)
  EventBus.emit(EventBus.events.ALARM_NEW, alarmData);
  // event_list.js (after)
  EventBus.on(EventBus.events.ALARM_NEW, () => loadEventList());
  ```

### R6. AlarmPopup _goDetail 큐 클리어 명시 [중 · 소]
- **왜 필요?**: 큐 전체 비우는 동작이 코드만으로 의도 불분명. 페이지 이동되니 OK이지만 코드 리뷰 시 의문.
- **장점**: 코드 의도 명확.
- **변경 위치**: [alarm-popup.js:107-119](../../../drf-server/static/js/shared/alarm-popup.js#L107-L119)
- **변경 예시**:
  ```js
  _goDetail() {
    const id = this._currentId;
    // 페이지 이동되므로 현재 큐는 의미 없음 (새 페이지에서 새로 받음)
    this._reset();
    window.location.href = id
      ? `/dashboard/monitoring/events/${id}/`
      : '/dashboard/monitoring/events/';
  },
  _reset() {
    clearTimeout(this._autoCloseTimer);
    this._currentId = null;
    this.isOpen = false;
    this.queue = [];
    document.getElementById('alarm-popup')?.style.setProperty('display', 'none');
  },
  ```

### R7. WSClient unsubscribe 패턴 활용 [하 · 소]
- **왜 필요?**: alarm-ws/worker-ws의 ws.onMessage 핸들러가 페이지 lifetime 동안 등록 — multi-page 환경에선 영향 미미. 그러나 SPA 도입 시 누수.
- **장점**: 미래 SPA 마이그레이션 대비.
- **변경 위치**: alarm-ws.js, worker-ws.js
- **변경 예시**:
  ```js
  // alarm-ws.js (after)
  (function () {
    let off = null;
    document.addEventListener('DOMContentLoaded', function () {
      const ws = WSClient.connect('/ws/sensors/');
      off = ws.onMessage(function (data) { ... });
    });
    window.addEventListener('beforeunload', () => off?.());
  })();
  ```

### R8. AlarmPopup _POPUP_CFG 노출 + freeze [하 · 소]
- **왜 필요?**: 모듈 상수 외부 변경 가능 — 의도치 않은 mutation 위험.
- **변경 위치**: [alarm-popup.js:9-28](../../../drf-server/static/js/shared/alarm-popup.js#L9-L28)
- **변경 예시**:
  ```js
  const _POPUP_CFG = Object.freeze({
    danger: Object.freeze({ ... }),
    warning: Object.freeze({ ... }),
  });
  ```

### R9. 자동 close 시간 상수화 [하 · 소]
- **왜 필요?**: 매직넘버 (10000, 5000) 변경 시 검색.
- **변경 위치**: [alarm-popup.js:95, 156](../../../drf-server/static/js/shared/alarm-popup.js#L95)
- **변경 예시**:
  ```js
  const POPUP_AUTO_CLOSE_MS = 10000;
  const TOAST_AUTO_CLOSE_MS = 5000;
  ```

### R10. AlarmPopup show의 분기 누락 보강 [하 · 소]
- **왜 필요?**: `level !== 'danger' && level !== 'warning'` 외 케이스 silent return — `'normal'`은 의도이나, 잘못된 값 (`undefined`, 오타) 또한 무시.
- **변경 위치**: [alarm-popup.js:40-42](../../../drf-server/static/js/shared/alarm-popup.js#L40-L42)
- **변경 예시**:
  ```js
  show(data) {
    const level = data.alarm_level;
    const VALID_LEVELS = ['danger', 'warning'];
    if (!VALID_LEVELS.includes(level)) {
      if (level !== 'normal') {
        console.warn('[AlarmPopup] unknown alarm_level:', level, data);
      }
      return;
    }
    // ...
  }
  ```

## 6. 단계별 적용 순서

### 1단계 — 즉시 (1일) ⚡
- **R1** alarm-mapper.js 추출 — 가장 큰 효과. 한 번에 3곳 정리.
- **R3** 서버 timestamp 사용 — R1과 함께 (mapper에서 처리).
- **R4** AlarmToast 호출 일관 (worker-ws에 추가 또는 명시 주석)
- **R10** show 분기 누락 console.warn
- **이유**: contract fragility 즉시 차단. R1·R3·R4·R10은 한 PR로 묶음 가능.

### 2단계 — 1주 내 🔧
- **R2** AlarmPopup 큐 정책 (운영팀 합의 후 옵션 결정)
- **R5** EventBus 패턴 도입 (event_list.js 등 다음 sprint와 연계)
- **R8** _POPUP_CFG freeze
- **R9** 자동 close 상수화
- **이유**: R2는 정책 결정 필요, R5는 다음 sprint 영향 큼. 핵심 로직 안정 후 리팩토링.

### 3단계 — 다음 sprint 🏗
- **R6** _goDetail _reset 추출
- **R7** unsubscribe 패턴 (SPA 마이그레이션 시점)
- **이유**: 미래 대비 또는 코드 정리.

### ⚠️ 주의사항 (초보자용)

- **R1 alarm-mapper.js 도입 시 스크립트 로드 순서 주의**: `<script src="...alarm-mapper.js">` 가 alarm-ws.js·worker-ws.js·dashboard/websocket.js 로드 **전**에 로드되어야 함. base.html / dashboard.html 등 모든 진입 템플릿 검사.
- **R2 큐 정책 변경은 e2e 테스트 회귀 필수**: PR-H 4종 테스트는 알람 누락·중복 시나리오를 검증. 변경 후 통과 확인.
- **R3 서버 timestamp 사용은 백엔드 contract 검증 필수**: alarm payload에 created_at 일관 포함 안 되면 fallback이 `new Date()`로 떨어짐 → 변경 효과 없음. 백엔드 grep 후 진행.
- **R5 EventBus 도입은 BREAKING 가능**: 기존 `document.dispatchEvent('newAlarmEvent')` 그대로 두면서 EventBus.emit 추가 → event_list.js를 EventBus로 마이그레이션 → 기존 dispatch 제거. 3 PR 권장.
- **R4 worker-ws 토스트 추가 시 worker_alert payload 검증**: 백엔드가 normal level의 worker_alert를 보내는지 확인. 안 보내면 추가 코드는 dead code (그래도 미래 대비).
