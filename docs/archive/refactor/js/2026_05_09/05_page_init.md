# 05. 페이지 진입 패턴 (initApp · loadMySafetyStatus · ui-exception 헬퍼)

## 1. 관련 파일 및 의존성

### 1.1 파일 목록
- [drf-server/static/js/shared/app-sub.js](../../../drf-server/static/js/shared/app-sub.js) — **12줄**, 서브 페이지 진입 IIFE
- [drf-server/static/js/dashboard/app.js](../../../drf-server/static/js/dashboard/app.js) — **49줄**, 대시보드 진입 + `loadMySafetyStatus`
- [drf-server/static/js/detail/ui-exception.js](../../../drf-server/static/js/detail/ui-exception.js) — **209줄**, 5개 글로벌 헬퍼 함수 + 모듈 상수

### 1.2 호출자 인벤토리
- **`initApp()`**: app.js와 app-sub.js 각자 정의·즉시 호출 (네임스페이스 충돌은 없으나 같은 이름)
- **`initHeaderAndSNB`**: app-sub.js, dashboard/app.js (둘 다 호출, 04에서 분석)
- **`initCharts`, `MapPanel.init`, `initWebSocket`, `EventPanel.init`, `loadMySafetyStatus`**: dashboard/app.js만 (다음 sprint 분석 대상)
- **`showChartOverlay/clearChartOverlay`**: detail/* 페이지의 차트 사용 시점 (다음 sprint)
- **`showSkeleton/clearSkeleton`**: 데이터 로딩 시
- **`grayOutBadges/restoreBadges`**: 데이터 stale 시 회색 처리
- **`startRetry`**: 데이터 fetch 실패 시 자동 재시도

### 1.3 의존성 그래프
```
페이지 HTML
    │
    ├─ <script src=".../shared/config.js">         (06에서 분석)
    ├─ <script src=".../shared/auth.js">           (01)
    ├─ <script src=".../shared/ws-client.js">      (02)
    ├─ <script src=".../shared/util.js">           (06)
    ├─ <script src=".../shared/layout.js">         (04)
    ├─ <script src=".../shared/alarm-popup.js">    (03)
    ├─ <script src=".../shared/alarm-ws.js">       (03)
    ├─ <script src=".../shared/worker-ws.js">      (03, 작업자 페이지만)
    │
    ├─ 대시보드 페이지:
    │   ├─ dashboard/charts.js
    │   ├─ dashboard/panels/*.js (event/map/scenario/worker)
    │   ├─ dashboard/websocket.js
    │   └─ dashboard/app.js                ← initApp() 호출
    │
    └─ 서브 페이지 (snb_details/*):
        ├─ detail/ui-exception.js          ← 헬퍼 글로벌 함수
        ├─ detail/<페이지전용>.js
        └─ shared/app-sub.js               ← initApp() 호출
```

## 2. 기능 흐름

### 2.1 대시보드 진입 흐름 (dashboard/app.js)
```
HTML 로드 → 모든 <script> 평가 완료 후
    │
    ▼ app.js의 즉시 실행
initApp() (async, await 없이 호출 — fire-and-forget)
    │
    ├─ await initHeaderAndSNB()       ─ 04에서 상세
    │   └─ Auth.getMe → renderUser/Menu/admin 등
    ├─ initCharts()                   ─ 동기, 차트 초기화 (다음 sprint)
    ├─ await MapPanel.init()          ─ 비동기 지도 데이터 로드
    ├─ initWebSocket()                ─ WSClient.connect 등록
    ├─ AlarmPopup.init()              ─ idempotent (이미 alarm-popup.js DOMContentLoaded에서 호출됨)
    ├─ AlarmToast.init()              ─ 동
    ├─ EventPanel.init()              ─ 이벤트 패널 (다음 sprint)
    └─ loadMySafetyStatus()           ─ /dashboard/api/safety-status/ fetch
```

### 2.2 서브 페이지 진입 흐름 (shared/app-sub.js)
```
HTML 로드 → 모든 <script> 평가 후
    │
    ▼ app-sub.js의 즉시 실행
initApp() (async)
    │
    └─ await initHeaderAndSNB()       ─ 04에서 상세
        ※ 차트·WebSocket·알람 init은 호출 안 함
        ※ 페이지별 JS가 자체적으로 차트·WS 초기화

initApp() 호출 끝 → 페이지별 JS의 DOMContentLoaded 핸들러가 본격 작업
```

### 2.3 ui-exception 헬퍼 사용 예
```
페이지 JS:
    fetch('/api/...')
        ├─ catch → showChartOverlay(canvas, 'error')
        ├─ data.length === 0 → showChartOverlay(canvas, 'empty')
        └─ ok → clearChartOverlay(canvas) + 차트 그리기

또는:
    const retry = startRetry(() => loadData(), 3000);
    // 성공 시 자동 stop, 페이지 언마운트 시 retry.stop()
```

## 3. 함수 분석

### 3.1 [shared/app-sub.js](../../../drf-server/static/js/shared/app-sub.js)

#### `initApp()` async (app-sub.js:7-9)
- **시그니처**: `async () => void`
- **역할**: 서브 페이지의 헤더·SNB 초기화 (차트·WS는 페이지별 JS가 자체 처리)
- **단계별 동작**:
  1. `await initHeaderAndSNB();` (8) — 04에서 상세 분석
- **호출하는 함수**: `initHeaderAndSNB` (layout.js)
- **호출자**: 자기 자신 즉시 (app-sub.js:11)
- **올바름 검증**:
  - ✅ 단순·명확.
  - ⚠️ **DOMContentLoaded 가드 없음** — 스크립트가 head에 있으면 DOM 미존재 시점에 initHeaderAndSNB 내부의 SNB.init이 NPE. base.html에 body 끝에 로드된다는 가정. 04 R6 (SNB DOM 참조 init 시점으로) 적용 시 해결.
  - 💡 **반환값 미사용** — initHeaderAndSNB가 user를 반환하지만 app-sub.js가 사용 안 함. 서브 페이지가 user 정보 필요 시 `Auth.getMe()` 또 호출 — 중복 fetch.

#### IIFE 즉시 호출 (app-sub.js:11)
- **시그니처**: `initApp();`
- **역할**: 모듈 로드 시 자동 실행
- **올바름 검증**:
  - ⚠️ **에러 핸들링 부재** — initApp 내부에서 throw 발생 시 unhandled promise rejection. 사용자에게 피드백 없음.

### 3.2 [dashboard/app.js](../../../drf-server/static/js/dashboard/app.js)

#### `initApp()` async (dashboard/app.js:14-24)
- **시그니처**: `async () => void`
- **역할**: 대시보드 진입 — 헤더·SNB + 차트 + 지도 + WS + 알람 + 이벤트 + 안전상태 모두 초기화
- **단계별 동작**:
  1. `await initHeaderAndSNB();` (15) — 헤더·SNB·메뉴 (사용자 인증 의존성 시작)
  2. `initCharts();` (17) — 동기, 차트 객체 생성 (다음 sprint)
  3. `await MapPanel.init();` (18) — 비동기, 지도 데이터 fetch (다음 sprint)
  4. `initWebSocket();` (19) — WSClient.connect + 핸들러 등록 (다음 sprint)
  5. `AlarmPopup.init();` (20) — **이미 alarm-popup.js DOMContentLoaded에서 호출됨** — idempotent라 OK
  6. `AlarmToast.init();` (21) — 동
  7. `EventPanel.init();` (22) — 이벤트 패널 (다음 sprint)
  8. `loadMySafetyStatus();` (23) — fire-and-forget
- **호출하는 함수**: `initHeaderAndSNB`, `initCharts`, `MapPanel.init`, `initWebSocket`, `AlarmPopup.init`, `AlarmToast.init`, `EventPanel.init`, `loadMySafetyStatus`
- **호출자**: 자기 자신 즉시 (dashboard/app.js:49)
- **올바름 검증**:
  - ✅ 순차 await + 동기 호출 적절히 혼용. 헤더 의존하는 모듈(Menu, admin버튼)이 먼저 await.
  - ⚠️ **DOMContentLoaded 가드 없음** — alarm-popup.js의 DOMContentLoaded보다 dashboard/app.js의 즉시 호출이 먼저면 AlarmPopup 객체는 정의되어 있지만 init이 두 번 호출됨 (idempotent로 OK).
  - ⚠️ **`AlarmPopup.init()`/`AlarmToast.init()` 명시 호출 의문** (이전 리뷰 03 hotspot 검증) — alarm-popup.js의 DOMContentLoaded가 자동 호출하므로 명시 호출 불필요. 단, **dashboard/app.js가 alarm-popup.js의 DOMContentLoaded보다 먼저 실행되는 시나리오**가 있으면 의미 있음. JS 평가 순서로 보면 동기 IIFE는 즉시, addEventListener는 등록만 — `initApp()` 즉시 호출이 DOMContentLoaded 전이면 명시 호출 효과 있음. 현재 안전.
  - ❌ **`initApp()` await 없이 즉시 호출** (dashboard/app.js:49) — 반환 Promise를 무시. 내부 await 실패 시 unhandled rejection. window.addEventListener('unhandledrejection') 핸들러 없으면 콘솔만.
  - ❌ **에러 핸들링 부재** — 어느 단계에서 실패해도 후속 단계 실행. 예: initHeaderAndSNB가 redirectLogin 후 return null이면 페이지 이동 중인데 initCharts 등 계속 실행 → 의미 없는 작업.
  - 💡 **AlarmPopup.init / AlarmToast.init이 alarm-popup.js DOMContentLoaded와 중복** — 명시 호출 제거 가능 (단, 위 시나리오 검증 필요).

#### `loadMySafetyStatus()` async (dashboard/app.js:29-47)
- **시그니처**: `async () => void`
- **역할**: 안전확인 상태 fetch + DOM 텍스트·클래스 갱신
- **단계별 동작**:
  1. **try** (30):
     - `const res = await fetch('/dashboard/api/safety-status/');` (31)
     - `if (!res.ok) return;` (32)
     - `const data = await res.json();` (33)
     - `checklistEl = getElementById('safety-checklist-status')` (35)
     - `vrEl = getElementById('safety-vr-status')` (36)
     - **if (checklistEl)** (38-41):
       - `textContent = data.checklist_done ? '완료' : '미완료'`
       - `className = data.checklist_done ? 'done' : 'todo'`
     - **if (vrEl)** (42-45): 동일 패턴
  2. **catch** (46): `/* 실패 시 기본값(미완료) 유지 */`
- **호출하는 함수**: `fetch`, `Response#json`, `document.getElementById`
- **호출자**: initApp 마지막
- **올바름 검증**:
  - ❌ **`fetch` 직접 사용 — Auth.apiFetch 미사용** — 이 endpoint(`/dashboard/api/safety-status/`)는 백엔드에서 `AllowAny`로 설정되어 있어 작동 (이전 리뷰 03 도메인 발견). **그러나 의도와 다른 동작**:
    1. 토큰 없이 호출 → 백엔드 세션 기반 응답 → 이전 사용자의 진도 유지 가능
    2. 토큰 만료 시 자동 refresh 안 함 → 옛 세션 데이터 응답
    3. 401 처리 부재 — 다른 페이지와 일관성 부족
  - ⚠️ **catch가 광범위 빈 블록** — 네트워크 에러, JSON 파싱 에러, DOM 부재 모두 silent. 디버깅 어려움. console.warn 권장.
  - ⚠️ **`!res.ok` 시 silent return** — 401·403·500 어떤 상태든 무시. 백엔드 변경 시 발견 늦음.
  - ✅ **DOM 부재 가드** (`if (checklistEl)`).
  - ✅ **textContent + className 사용** — XSS 안전.
  - 💡 `'완료'/'미완료'` 한글 매직스트링.
  - 💡 `'done'/'todo'` className 매직스트링.

#### IIFE 즉시 호출 (dashboard/app.js:49)
- **시그니처**: `initApp();`
- **역할**: 모듈 로드 시 자동 실행
- **올바름 검증**:
  - ⚠️ await 없이 호출 → unhandled rejection 가능. (위 ❌ 참조)

### 3.3 [detail/ui-exception.js](../../../drf-server/static/js/detail/ui-exception.js)

#### 모듈 상수 (ui-exception.js:16-23)
- `OVERLAY_ATTR = 'data-ui-overlay'`
- `SKELETON_ATTR = 'data-ui-skeleton'`
- `GRAY_ATTR = 'data-ui-gray'`
- `MSG = { error: '데이터를 불러올 수 없습니다.', empty: '데이터가 존재하지 않습니다.' }`

#### `showChartOverlay(canvas, type)` (ui-exception.js:32-62)
- **시그니처**: `(canvas: HTMLCanvasElement, type: 'error'|'empty') => void`
- **역할**: 차트 위에 반투명 텍스트 오버레이를 띄움
- **단계별 동작**:
  1. `if (!canvas) return;` (33)
  2. `clearChartOverlay(canvas);` (35) — 기존 오버레이 제거
  3. `const wrap = canvas.parentElement; if (!wrap) return;` (37-38)
  4. `if (getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';` (41-42) — 부모 position 보정
  5. overlay div 생성 (44-58):
     - `setAttribute(OVERLAY_ATTR, type)` — 식별자
     - 인라인 style 설정 (position absolute, inset 0, flex center, opacity 0.75 등)
  6. `overlay.textContent = MSG[type] ?? MSG.error;` (59) — fallback to error
  7. `wrap.appendChild(overlay);` (61)
- **호출하는 함수**: `getComputedStyle`, `document.createElement`, `Element#setAttribute`, `Element#appendChild`
- **호출자**: detail/* 페이지의 차트 fetch 실패 시
- **올바름 검증**:
  - ✅ canvas null + parentElement null 가드.
  - ✅ position static 보정 — overlay가 의도한 위치에 떠야 하므로 필요.
  - ✅ textContent — XSS 안전.
  - ✅ MSG fallback — 잘못된 type도 안전.
  - ⚠️ **인라인 style cssText** — CSS class로 분리하면 디자인 시스템과 일관. 단, **shimmer 애니메이션과 달리 정적 스타일이라 큰 문제 아님**.
  - ⚠️ **wrap.style.position = 'relative' 영속** — 한 번 설정되면 다른 위치에서 부작용 가능. clearChartOverlay에서 복원 안 됨. 정상 동작 — relative는 다른 자식에 영향 없음.
  - 💡 `MSG[type] ?? MSG.error` — `??`는 null/undefined만, `||`였으면 빈 문자열도 fallback. nullish coalescing이 더 정확.

#### `clearChartOverlay(canvas)` (ui-exception.js:68-73)
- **시그니처**: `(canvas: HTMLCanvasElement) => void`
- **역할**: 부모에 붙어있는 모든 overlay 제거
- **단계별 동작**:
  1. `if (!canvas) return;` (69)
  2. `const wrap = canvas.parentElement; if (!wrap) return;` (70-71)
  3. `wrap.querySelectorAll([${OVERLAY_ATTR}]).forEach(el => el.remove());` (72)
- **올바름 검증**:
  - ✅ 단순·정확.
  - 💡 한 번에 여러 overlay 제거 — 정상.

#### `showSkeleton(container, count = 8)` (ui-exception.js:84-118)
- **시그니처**: `(container: HTMLElement, count?: number) => void`
- **역할**: container 안에 스켈레톤 카드를 count개 삽입
- **단계별 동작**:
  1. `if (!container) return;` (85)
  2. `clearSkeleton(container);` (87)
  3. `const frag = document.createDocumentFragment();` (89) — DocumentFragment 사용 (성능)
  4. for 루프 count번 (90-101):
     - `card = document.createElement('div'); setAttribute(SKELETON_ATTR, ''); style.cssText = ...gradient... animation: skeleton-shimmer...`
     - `frag.appendChild(card);`
  5. `if (!getElementById('skeleton-style'))` 분기 (104-114):
     - `<style id="skeleton-style">@keyframes skeleton-shimmer {...}</style>` 한 번만 주입
  6. `container.innerHTML = ''; container.appendChild(frag);` (116-117)
- **호출자**: detail 페이지 데이터 로딩 시
- **올바름 검증**:
  - ✅ DocumentFragment + appendChild — reflow 1회. 성능 모범.
  - ✅ keyframes 한 번만 주입 — 중복 방지 가드.
  - ✅ container null 가드.
  - ⚠️ **`container.innerHTML = ''`** — 기존 자식 노드의 이벤트 리스너 자동 제거 (DOM 분리). 외부 참조 있으면 메모리 누수 가능. 호출자가 fetch 결과 카드를 다시 추가하니 정상.
  - ⚠️ **인라인 style 큰 cssText** — 디자인 토큰화 시 어려움.
  - 💡 `count = 8` 기본값 — 8개 스켈레톤. 적절.

#### `clearSkeleton(container)` (ui-exception.js:124-127)
- **시그니처**: `(container: HTMLElement) => void`
- **역할**: 스켈레톤 카드만 제거 (다른 자식은 유지)
- **단계별 동작**:
  1. `container?` 가드
  2. `querySelectorAll([${SKELETON_ATTR}]).forEach(remove)`
- **올바름 검증**:
  - ✅ data 속성으로 식별 — 다른 자식과 공존 안전.
  - ✅ 정상.

#### `grayOutBadges(container)` (ui-exception.js:137-151)
- **시그니처**: `(container: HTMLElement) => void`
- **역할**: 상태 badge·dot을 회색으로 강제 변환 (stale 데이터 시각화)
- **단계별 동작**:
  1. `container?` 가드
  2. `querySelectorAll('.status-badge, .card-status-dot, .dot-sq')` — 3개 클래스 매칭
  3. forEach:
     - `if (el.hasAttribute(GRAY_ATTR)) return;` (144) — 중복 변환 방지
     - `el.setAttribute(GRAY_ATTR, el.className);` (145) — 원래 className 보존
     - `el.classList.remove('danger', 'caution', 'safe');` (147) — 위험도 클래스 제거
     - `el.classList.add('gray');` (148)
     - `el.style.opacity = '0.4';` (149)
- **올바름 검증**:
  - ✅ `data-ui-gray` 속성으로 idempotent.
  - ✅ 원본 className 보존 — restoreBadges가 복원 가능.
  - ❌ **`'caution', 'safe'` 클래스명** — 백엔드 enum은 `'warning', 'normal'`. **CSS 클래스가 다른 네임 사용** — 의도된 디자인 토큰 분리일 수도 있고, util.js levelLabel과 같은 불일치(이전 리뷰 08 H1)일 수도. **검증 필요**: HTML/CSS에서 `.caution`/`.safe` 실제 정의되어 있는지.
  - ⚠️ **`el.style.opacity = '0.4'`** — 인라인 style. CSS class `.gray`가 opacity를 설정한다면 중복.

#### `restoreBadges(container)` (ui-exception.js:157-165)
- **시그니처**: `(container: HTMLElement) => void`
- **역할**: grayOutBadges로 변환된 badge를 원래대로 복원
- **단계별 동작**:
  1. `querySelectorAll([${GRAY_ATTR}])`
  2. forEach:
     - `el.className = el.getAttribute(GRAY_ATTR);` — 원본 복원
     - `el.style.opacity = '';` — 인라인 style 제거
     - `el.removeAttribute(GRAY_ATTR);`
- **올바름 검증**:
  - ✅ 정상. 데이터 속성 → className 복원 패턴 명확.

#### `startRetry(fetchFn, intervalMs = 3000)` (ui-exception.js:183-208)
- **시그니처**: `(fetchFn: () => Promise<any>, intervalMs?: number) => { stop: () => void }`
- **역할**: fetchFn 실패 시 일정 간격으로 재시도, 성공 시 자동 stop
- **단계별 동작**:
  1. `let timer = null; let stopped = false;` (184-185)
  2. `attempt()` 내부 함수 정의 (187-198):
     - `if (stopped) return;`
     - `try { await fetchFn(); stopped = true; }` — 성공 시 자동 중단
     - `catch { if (!stopped) timer = setTimeout(attempt, intervalMs); }`
  3. `attempt();` (200) — 즉시 1회
  4. `return { stop() { stopped = true; if (timer !== null) clearTimeout(timer); } };` (202-207)
- **호출자**: detail 페이지 데이터 fetch 실패 시
- **올바름 검증**:
  - ✅ **closure 패턴** — stop 함수가 timer/stopped 캡처.
  - ✅ 즉시 1회 + 실패 시 재시도 — 직관.
  - ✅ stop 후 attempt 진입 시 즉시 return.
  - ⚠️ **stopped 플래그 race** — `await fetchFn()` 중 stop 호출되면 stopped=true 후 stopped=true로 다시 설정 (변경 없음). 정상.
  - ⚠️ **무한 재시도** — 영구 실패 시 영구 재시도. 02의 R1 (지수 백오프)과 동일 이슈. ui-exception.js의 retry는 작은 규모라 영향 미미.
  - 💡 fetchFn 인자 없음 — 호출자가 closure로 처리. 좋은 단순함.
  - 💡 stop 후 fetchFn이 in-flight면 결과는 반영 — stopped=true로 단지 다음 재시도 안 함. 의도일 수 있으나 명시 부족.

## 4. 종합 평가

### 강점
- ✅ **`initApp` 패턴 — 페이지 진입 단일 함수** — 명확.
- ✅ **DocumentFragment 활용** — showSkeleton의 reflow 최적화.
- ✅ **데이터 속성으로 idempotent 식별** — 중복 변환 방지.
- ✅ **className 보존·복원 패턴** — grayOut/restore.
- ✅ **closure로 stop 함수 캡처** — startRetry.
- ✅ **null 가드 일관 적용** — 모든 헬퍼.
- ✅ **textContent 사용** — XSS 안전.

### 약점
- ❌ **dashboard/app.js의 await 없는 즉시 호출** — unhandled rejection.
- ❌ **loadMySafetyStatus가 Auth.apiFetch 미사용** — 인증 일관성 결여.
- ❌ **'caution', 'safe' 클래스명** — 백엔드 enum과 불일치 가능 (검증 필요).
- ⚠️ **DOMContentLoaded 가드 없음** — head 로드 시 NPE 위험.
- ⚠️ **인라인 style 다수** — 디자인 시스템 일관성 결여.

### 중복 / 누락
- 📌 **app.js와 app-sub.js가 같은 `initApp` 이름** — 한 페이지에 둘 다 로드되면 후자가 전자를 덮어씀. 의도된 동작은 같은 이름 → 한쪽만 로드하면 됨. 이름 충돌 가능성 (사소).
- 📌 **에러 처리 일관성 부재** — initApp 중 한 단계 실패 시 나머지 어떻게 처리할지 미정의.
- 📌 **에러 메시지 한글 매직스트링** — i18n 시 추출 필요.

### contract 정합성
- ✅ ui-exception.js의 헬퍼는 자체 규약 (data 속성, MSG dict).
- ⚠️ `caution`, `safe` 클래스 — CSS와의 contract. 백엔드 enum과 어긋남.

## 5. 리팩토링 권고

### R1. dashboard/app.js의 initApp 에러 핸들링 [상 · 소]
- **왜 필요?**: await 없이 호출 + 에러 처리 부재 → unhandled promise rejection. 사용자에게 "왜 화면이 안 뜨지?" 디버깅 어려움.
- **장점**: 명시적 에러 노출 / 운영 모니터링 가능.
- **단점**: 없음.
- **변경 위치**: [dashboard/app.js:49](../../../drf-server/static/js/dashboard/app.js#L49), [app-sub.js:11](../../../drf-server/static/js/shared/app-sub.js#L11)
- **변경 예시**:
  ```js
  // before
  initApp();

  // after
  initApp().catch(err => {
    console.error('[app] initialization failed:', err);
    // 사용자 피드백 — 빈 화면보다 명시적 에러 페이지
    document.body.innerHTML = '<div style="padding:40px;text-align:center">페이지 로드 실패. 새로고침해주세요.</div>';
  });
  ```
  ※ 더 나은 옵션: `window.addEventListener('unhandledrejection', ...)` 글로벌 핸들러로 통합.

### R2. loadMySafetyStatus → Auth.apiFetch [상 · 소]
- **왜 필요?**: 직접 fetch는 인증 헤더 없음 + 401 자동 refresh 부재 + 토큰 만료 처리 결여. 다른 페이지와 일관성 결여.
- **장점**: 인증 일관 / 자동 refresh / 401 시 redirectLogin.
- **단점**: 백엔드가 AllowAny 유지 시 토큰 없어도 동작 — 변경 후에도 호환. **그러나 이전 리뷰 03 C2 (AllowAny → IsAuthenticated)이 적용되면 이 fetch는 401 받아 무시됨**. 조기에 apiFetch 사용해야 안전.
- **변경 위치**: [dashboard/app.js:31](../../../drf-server/static/js/dashboard/app.js#L31)
- **변경 예시**:
  ```js
  // before
  async function loadMySafetyStatus() {
    try {
      const res = await fetch('/dashboard/api/safety-status/');
      if (!res.ok) return;
      const data = await res.json();
      ...
    } catch { /* 실패 시 기본값(미완료) 유지 */ }
  }

  // after
  async function loadMySafetyStatus() {
    try {
      const res = await Auth.apiFetch('/dashboard/api/safety-status/');
      if (!res.ok) {
        console.warn('[safety-status] fetch failed:', res.status);
        return;
      }
      const data = await res.json();
      ...
    } catch (e) {
      console.warn('[safety-status] error:', e);
    }
  }
  ```

### R3. 'caution'·'safe' vs 'warning'·'normal' contract 정합 [상 · 중]
- **왜 필요?**: 백엔드 RiskLevel enum은 `warning`/`normal`. CSS 클래스는 `caution`/`safe`. ui-exception.js가 grayOutBadges에서 `caution`/`safe`를 제거하는데, 실제 DOM에 이 클래스가 적용되는지 검증 필요.
- **장점**: 진실 원천 단일화.
- **단점**: CSS 변경 + JS 변경 동시 필요 (대규모).
- **변경 위치**: 전 시스템 — CSS 파일·JS 다수.
- **변경 예시 (옵션 A: CSS 클래스를 백엔드와 통일)**:
  ```css
  /* before */
  .status-badge.caution { background: orange; }
  .status-badge.safe    { background: green; }

  /* after */
  .status-badge.warning { background: orange; }
  .status-badge.normal  { background: green; }
  ```
  ```js
  // ui-exception.js after
  el.classList.remove('danger', 'warning', 'normal');
  ```
- **변경 예시 (옵션 B: JS 매핑 함수)**:
  ```js
  // shared/level-mapper.js (신규)
  const LEVEL_TO_CLASS = { danger: 'danger', warning: 'caution', normal: 'safe' };
  function levelClass(level) { return LEVEL_TO_CLASS[level] || ''; }
  ```
  ※ 옵션 A가 단순하지만 마이그레이션 비용 큼. 옵션 B는 매번 변환 — 06의 levelLabel과 통합 가능.

### R4. dashboard/app.js의 명시 init 호출 정리 [중 · 소]
- **왜 필요?**: AlarmPopup.init / AlarmToast.init이 alarm-popup.js의 DOMContentLoaded와 중복 (idempotent라 OK이지만 의도 불명확).
- **장점**: 코드 명확.
- **단점**: 없음 (기능 변화 없음).
- **변경 위치**: [dashboard/app.js:20-21](../../../drf-server/static/js/dashboard/app.js#L20-L21)
- **변경 예시**:
  ```js
  // before
  AlarmPopup.init();
  AlarmToast.init();

  // after — 제거 (alarm-popup.js DOMContentLoaded가 자동 호출)
  // 또는 명시 주석
  // AlarmPopup/AlarmToast.init은 alarm-popup.js DOMContentLoaded에서 자동 실행
  ```

### R5. ui-exception.js 인라인 style → CSS class [중 · 중]
- **왜 필요?**: 디자인 시스템 일관성. 디자이너가 색상·크기 변경 시 JS 수정 필요.
- **장점**: 디자인 토큰 활용 / CSS 변수 사용.
- **단점**: CSS 파일 추가. 동적 부분(opacity 0.4)은 그대로 인라인 또는 CSS 변수.
- **변경 위치**: [ui-exception.js:46-58, 93-99](../../../drf-server/static/js/detail/ui-exception.js#L46)
- **변경 예시**:
  ```css
  /* static/css/components/ui-exception.css */
  [data-ui-overlay] {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    color: #8b949e;
    opacity: 0.75;
    pointer-events: none;
    text-align: center;
    padding: 4px;
  }
  [data-ui-skeleton] {
    background: linear-gradient(90deg, #1c2128 25%, #262d36 50%, #1c2128 75%);
    background-size: 200% 100%;
    animation: skeleton-shimmer 1.4s infinite;
    border-radius: 8px;
    border: 1px solid #30363d;
  }
  @keyframes skeleton-shimmer {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
  ```
  ```js
  // ui-exception.js after
  function showChartOverlay(canvas, type) {
    if (!canvas) return;
    clearChartOverlay(canvas);
    const wrap = canvas.parentElement;
    if (!wrap) return;
    if (getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';
    const overlay = document.createElement('div');
    overlay.setAttribute(OVERLAY_ATTR, type);
    overlay.textContent = MSG[type] ?? MSG.error;
    wrap.appendChild(overlay);
  }
  ```

### R6. catch 광범위 → console.warn (loadMySafetyStatus) [중 · 소]
- **왜 필요?**: 디버깅 어려움.
- **변경 위치**: [dashboard/app.js:46](../../../drf-server/static/js/dashboard/app.js#L46)
- **변경 예시**: R2와 함께 (이미 포함).

### R7. startRetry 지수 백오프 옵션 [하 · 소]
- **왜 필요?**: 영구 실패 시 무한 재시도. 작은 규모지만 일관성 위해 백오프 옵션 추가.
- **변경 위치**: [ui-exception.js:183-208](../../../drf-server/static/js/detail/ui-exception.js#L183-L208)
- **변경 예시**:
  ```js
  function startRetry(fetchFn, opts = {}) {
    const initialMs = opts.initialMs || 3000;
    const maxMs = opts.maxMs || 30000;
    const factor = opts.factor || 1.5;  // 1.5x씩 증가
    const maxAttempts = opts.maxAttempts || 10;

    let timer = null, stopped = false, attempts = 0;

    async function attempt() {
      if (stopped) return;
      attempts++;
      try {
        await fetchFn();
        stopped = true;
      } catch {
        if (!stopped && attempts < maxAttempts) {
          const delay = Math.min(initialMs * Math.pow(factor, attempts - 1), maxMs);
          timer = setTimeout(attempt, delay);
        }
      }
    }
    attempt();
    return { stop() { stopped = true; if (timer !== null) clearTimeout(timer); } };
  }
  ```

### R8. initApp 이름 충돌 명시화 [하 · 소]
- **왜 필요?**: app.js와 app-sub.js가 같은 함수명 — 한 페이지에 둘 다 로드되면 충돌. 현재는 분기되어 한쪽만 로드되니 안전, 그러나 의도 명확화.
- **변경 위치**: 두 파일.
- **변경 예시**:
  ```js
  // app-sub.js
  async function initSubApp() {  // 이름 변경
    await initHeaderAndSNB();
  }
  initSubApp();
  ```

### R9. ui-exception.js 모듈 패턴 [하 · 소]
- **왜 필요?**: 5개 헬퍼가 글로벌 함수로 노출 — 네임스페이스 오염.
- **변경 위치**: [ui-exception.js](../../../drf-server/static/js/detail/ui-exception.js)
- **변경 예시**:
  ```js
  const UIException = {
    showChartOverlay,
    clearChartOverlay,
    showSkeleton,
    clearSkeleton,
    grayOutBadges,
    restoreBadges,
    startRetry,
  };
  // 사용처는 UIException.showChartOverlay(...)
  ```
  ※ 이미 호출자가 많으면 마이그레이션 비용 큼. 새 코드에서만 사용.

### R10. loadMySafetyStatus의 매직스트링 추출 [하 · 소]
- **왜 필요?**: '완료'/'미완료', 'done'/'todo' 매직스트링.
- **변경 위치**: [dashboard/app.js:39-40, 43-44](../../../drf-server/static/js/dashboard/app.js#L39-L40)
- **변경 예시**:
  ```js
  const STATUS_LABEL = { done: '완료', todo: '미완료' };
  ...
  if (checklistEl) {
    const key = data.checklist_done ? 'done' : 'todo';
    checklistEl.textContent = STATUS_LABEL[key];
    checklistEl.className = key;
  }
  ```

## 6. 단계별 적용 순서

### 1단계 — 즉시 (1일) ⚡
- **R1** initApp 에러 핸들링 — `.catch()` 한 줄.
- **R2** loadMySafetyStatus → Auth.apiFetch — 1줄 변경.
- **R6** catch console.warn (R2와 함께).
- **R4** AlarmPopup/AlarmToast.init 정리 (확인 후 제거 또는 주석).
- **이유**: 모두 작은 변경. 인증·에러 가시성 즉시 향상.

### 2단계 — 1주 내 🔧
- **R3** caution/safe vs warning/normal 정합 — **운영 합의 필요**. 옵션 결정 후.
- **R5** 인라인 style → CSS class.
- **이유**: R3은 큰 변경이라 사전 검증 필수. R5는 디자인 시스템 정착.

### 3단계 — 다음 sprint 🏗
- **R7** startRetry 백오프 (호출자 마이그레이션).
- **R8** initApp 이름 충돌 정리.
- **R9** UIException 모듈 패턴 (대규모 마이그레이션).
- **R10** 매직스트링 추출.

### ⚠️ 주의사항 (초보자용)

- **R1 적용 시 unhandledrejection 글로벌 핸들러 권장**: `.catch()` 외에 `window.addEventListener('unhandledrejection', ...)` 추가하면 다른 비동기 코드의 에러도 잡힘. base.html에 한 번만 등록.
- **R2 적용 후 e2e 회귀 검증**: 이전 리뷰 03 C2가 백엔드에서 적용되면 (AllowAny → IsAuthenticated) 함께 통과해야. 변경 순서: ① loadMySafetyStatus apiFetch 사용 → ② 백엔드 권한 변경 → ③ e2e 검증.
- **R3 caution/safe 변경은 사전 grep 필수**: `grep -rn 'caution\|safe' static/css static/js templates`. 변경 누락 시 색상 깨짐. 점진 마이그레이션 권장 — 디자인 토큰부터 시작.
- **R5 CSS 분리 시 specificity 주의**: `[data-ui-overlay]` 셀렉터의 specificity가 인라인 style보다 약함. `!important`는 피하고, 호출자가 인라인 style을 덮어쓰지 않는지 확인.
- **모든 변경 후 페이지 진입 4종 시나리오 검증**: 1) 정상 / 2) 토큰 만료 / 3) 백엔드 5xx / 4) 네트워크 끊김. initApp이 각 단계에서 어떻게 동작하는지 콘솔 로그 추적.
