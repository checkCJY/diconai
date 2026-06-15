# 04. 레이아웃·메뉴·헤더 (SNB · Menu · Header · initHeaderAndSNB)

## 1. 관련 파일 및 의존성

### 1.1 파일 목록
- [drf-server/static/js/shared/layout.js](../../../drf-server/static/js/shared/layout.js) — 251줄, **`SNB`(3 메서드) + `Menu`(2 메서드) + `Header`(8 메서드) + `initHeaderAndSNB`(top-level async)**
- [drf-server/templates/components/header.html](../../../drf-server/templates/components/header.html) — 헤더 마크업 (의존)
- [drf-server/templates/components/admin_sidebar.html](../../../drf-server/templates/components/admin_sidebar.html) — SNB 마크업 (의존)
- 의존: [01 Auth](01_auth_session.md), [06 util.js의 pad/nowDateLabel](06_utils_config.md)

### 1.2 호출자 인벤토리
- **`initHeaderAndSNB`** 호출:
  - [shared/app-sub.js:8](../../../drf-server/static/js/shared/app-sub.js#L8) — 서브 페이지 진입
  - [dashboard/app.js](../../../drf-server/static/js/dashboard/app.js) — 대시보드 진입 (05에서 분석)
- 외부 노출: `SNB`, `Menu`, `Header`, `initHeaderAndSNB` 모두 글로벌 (let/const 없이 정의)
- `Header.adminUrl`은 `initHeaderAndSNB`가 user.admin_url로 설정 → `Header.handleAdmin`이 사용

### 1.3 의존성 그래프
```
페이지 (app.js / app-sub.js)
    │
    ▼ initHeaderAndSNB() 호출
        │
        ├─ Auth.getAccessToken() — 토큰 부재 시 redirectLogin
        ├─ Auth.getMe() — /api/auth/me/ 호출 (메뉴·역할 조회)
        ├─ Header.renderUser(username, role)
        ├─ Header.showAdminBtn(role)
        ├─ Menu.render(menu_tree) — SNB DOM 렌더링
        ├─ Header.adminUrl 설정
        ├─ Auth.setRole(role)
        ├─ SNB.init() — 햄버거·overlay 이벤트 바인딩
        ├─ Header.init() — initClock + initLogout + 새로고침/홈/관리자 바인딩
        └─ Header.updateLastUpdated()
```

## 2. 기능 흐름

### 2.1 페이지 진입 → 사용자 정보 fetch → 헤더·SNB 초기화
```
페이지 로드 → app.js / app-sub.js
    │
    ▼ initHeaderAndSNB() (await)
1. Auth.getAccessToken() → 없으면 redirectLogin + return null
2. Auth.getMe() → /api/auth/me/
   ├─ 응답 ok → user 객체 (id, username, role, menu_tree, admin_url?)
   │   ├─ Header.renderUser(user.username, user.role) — 헤더에 이름·역할 표시
   │   ├─ Header.showAdminBtn(user.role) — 관리자면 어드민 버튼 노출
   │   ├─ Menu.render(user.menu_tree) — SNB에 메뉴 트리 렌더
   │   ├─ Header.adminUrl = user.admin_url (있으면)
   │   └─ Auth.setRole(user.role) — localStorage 갱신
   └─ 실패 → user=null
        ├─ Header.renderUser(localStorage.username || '-')
        └─ Menu.showError() — "메뉴를 불러올 수 없습니다"
3. SNB.init() — 햄버거 클릭 핸들러
4. Header.init() — initClock + initLogout + 5개 버튼 바인딩
5. Header.updateLastUpdated() — 헤더에 현재 시각 표시
```

### 2.2 SNB 토글 흐름
```
사용자 → 햄버거 버튼 클릭
    │
    ▼ SNB.toggle()
drawer.classList contains 'open'?
    ├─ Yes → SNB.close() (drawer + overlay 'open' 제거)
    └─ No → SNB.open() (drawer + overlay 'open' 추가)

사용자 → overlay (배경) 클릭
    └─ SNB.close()

메뉴 항목 클릭 → window.location.href + SNB.close()
```

### 2.3 헤더 새로고침 흐름
```
사용자 → 새로고침 버튼 클릭
    │
    ▼ Header.handleRefresh()
1. isRefreshing 플래그 체크 — 진행 중이면 return (debounce)
2. isRefreshing = true, btn에 'spinning' class 추가
3. try:
   ├─ Auth.apiFetch('/dashboard/api/refresh/')
   ├─ 401 → Auth.redirectLogin (return)
   ├─ res.json() → admin_url 있으면 노출
   ├─ updateLastUpdated()
   └─ EventPanel?.loadEventList() — 대시보드의 이벤트 패널 재로드
4. catch (네트워크 에러 등):
   └─ btn 색상 빨강 + tooltip 변경, 3초 후 복원
5. finally:
   ├─ isRefreshing = false
   └─ btn에서 'spinning' class 제거
```

## 3. 함수 분석

### 3.1 [shared/layout.js](../../../drf-server/static/js/shared/layout.js) — `SNB` 객체

#### SNB 객체 구조 (layout.js:12-24)
```js
const SNB = {
  drawer:  document.getElementById('snbDrawer'),    // 모듈 로드 시점
  overlay: document.getElementById('snbOverlay'),
  open()   { ... },
  close()  { ... },
  toggle() { ... },
  init() { ... },
};
```
- **올바름 검증**:
  - ❌ **`document.getElementById`가 모듈 로드 시점** (layout.js:13-14) — layout.js가 head에 로드되면 DOM 미존재 시점이라 null. body 끝 또는 DOMContentLoaded 후 로드라면 OK. **현재 base.html에서 layout.js 로드 시점 확인 필요**. 문제면 SNB.drawer === null → open/close에서 NPE.
  - ⚠️ DOM 부재 시 `?.` 옵셔널 체이닝 없음 — 부분 페이지(에러 페이지 등)에선 NPE 위험.

#### `SNB.open()` (layout.js:16)
- **시그니처**: `() => void`
- **역할**: drawer + overlay에 'open' 클래스 추가
- **단계별 동작**:
  1. `this.drawer.classList.add('open');`
  2. `this.overlay.classList.add('open');`
- **올바름 검증**:
  - ✅ 단순.
  - ❌ this.drawer 또는 this.overlay null이면 NPE.

#### `SNB.close()` (layout.js:17)
- **시그니처**: `() => void`
- **역할**: 'open' 클래스 제거
- **올바름 검증**: ✅ 단순. 같은 NPE 위험.

#### `SNB.toggle()` (layout.js:18)
- **시그니처**: `() => void`
- **역할**: 현재 상태 반대로 전환
- **단계별 동작**:
  1. `this.drawer.classList.contains('open') ? this.close() : this.open();`
- **올바름 검증**: ✅ 정상.

#### `SNB.init()` (layout.js:20-23)
- **시그니처**: `() => void`
- **역할**: 햄버거 + overlay 이벤트 바인딩
- **단계별 동작**:
  1. `document.getElementById('hamburger')?.addEventListener('click', () => this.toggle());`
  2. `this.overlay?.addEventListener('click', () => this.close());`
- **올바름 검증**:
  - ✅ 옵셔널 체이닝 — DOM 부재 안전.
  - 💡 `init()`에서만 안전 패턴 — open/close/toggle은 unsafe. 일관성 부족.

### 3.2 [shared/layout.js](../../../drf-server/static/js/shared/layout.js) — `Menu` 객체 (layout.js:30-103)

#### `Menu` 모듈 상수
- `currentPath: window.location.pathname` (layout.js:31) — 현재 경로
- `iconMap: {shield, monitor, settings}` (layout.js:33-37) — SVG 인라인 마크업 3개

#### `Menu.render(menuTree)` (layout.js:40-100)
- **시그니처**: `(menuTree: Array<MenuNode>) => void`
- **역할**: 메뉴 트리를 SNB DOM으로 렌더링하고 아코디언 구조 설정
- **단계별 동작**:
  1. `const container = document.getElementById('snbMenu');` (layout.js:41)
  2. `const errDiv = document.getElementById('snbError');` (layout.js:42)
  3. `if (!menuTree || menuTree.length === 0) { errDiv.style.display = 'block'; return; }` (layout.js:44)
  4. `errDiv.style.display = 'none';` (layout.js:45)
  5. `const ul = document.createElement('ul'); ul.className = 'snb-depth1';` (layout.js:47-48)
  6. `menuTree.forEach((menu) => {` (layout.js:50)
     - `li`, `hasChildren`, `icon` 결정 (51-54)
     - `btn = document.createElement('button')` (56)
     - `btn.innerHTML = '<span class="menu-icon">${icon}</span>...'` (59-63) — **innerHTML + ${icon}** ⚠️
     - `li.appendChild(btn)` (64)
     - hasChildren 분기 (66-93):
       - subUl 생성 (67-69)
       - menu.children.forEach: subLi 생성, **innerHTML로 `<a href="${child.path}">${child.label}</a>`** (71-75)
       - btn 클릭 시 expanded 토글 (79-83)
       - currentPath 매칭 시 자동 expand (85-88)
       - submenu의 a 클릭 시 SNB.close (90)
     - else if menu.path: btn 클릭 시 navigate (91-93)
     - `ul.appendChild(li)` (95)
  7. `container.innerHTML = ''; container.appendChild(ul);` (98-99)
- **호출하는 함수**: `document.getElementById`, `document.createElement`, `Element#appendChild`, `forEach`
- **호출자**: initHeaderAndSNB
- **올바름 검증**:
  - ❌ **`btn.innerHTML = ...${menu.label}...`** (layout.js:60-62) — menu.label이 백엔드에서 오는 데이터라 현재는 안전, 그러나 **XSS 패턴 정착 부족** — 사용자 데이터가 들어오는 케이스로 확장 시 즉시 위험. (이전 리뷰 08 H3)
  - ❌ **`subLi.innerHTML = '<a href="${child.path}">${child.label}</a>'`** (layout.js:74) — 같은 문제. child.path가 검증 안 된 URL이면 javascript: 스킴 가능.
  - ⚠️ **iconMap 미정의 시 `'•'` 폴백** (layout.js:54) — silent fallback. 새 아이콘 키 추가 시 디자인 깨짐 발견 늦음. (이전 리뷰 08 H7)
  - ⚠️ **container.innerHTML = ''로 기존 노드 제거** (layout.js:98) — 기존 노드의 이벤트 리스너 자동 제거 (DOM removal로). 그러나 외부 참조가 있으면 메모리 누수 가능. 현재 패턴은 안전.
  - ⚠️ **errDiv null 가드 없음** (layout.js:42-44) — `if (!menuTree)` 분기에서 errDiv null이면 NPE. DOM 부재 페이지에선 에러.
  - ⚠️ **menu/child의 누락 키 가드 부재** — `menu.id`, `menu.label`, `menu.children`, `child.path`, `child.label` 모두 검증 없음. 백엔드 응답 형식 어긋나면 NPE 또는 `undefined` 노출.
  - 💡 SVG 인라인 — sprite 패턴 미사용 (이전 리뷰 08 H4).
  - 💡 `data-id`, `data-path` 사용 — DOM 데이터 패턴. 정상.

#### `Menu.showError()` (layout.js:102)
- **시그니처**: `() => void`
- **역할**: snbError div 노출 (메뉴 로드 실패 시)
- **올바름 검증**:
  - ✅ 단순.
  - ⚠️ DOM 부재 시 NPE — `?.` 옵셔널 체이닝 부재.

### 3.3 [shared/layout.js](../../../drf-server/static/js/shared/layout.js) — `Header` 객체 (layout.js:109-224)

#### `Header` 모듈 상태
- `isRefreshing: false` (110) — 새로고침 debounce 플래그
- `adminUrl: null` (111) — 관리자 페이지 URL (initHeaderAndSNB가 설정)

#### `Header.initClock()` (layout.js:113-124)
- **시그니처**: `() => void`
- **역할**: 헤더 시계 시작 (1초 간격 setInterval)
- **단계별 동작**:
  1. `const clockEl = document.getElementById('clock');` (114)
  2. `const tick = () => { ... }` 내부 함수 정의 (115-122)
     - clockEl null이면 return
     - `${year}.${pad(month+1)}.${pad(date)} ${pad(h)}:${pad(m)}:${pad(s)}` 포맷
  3. `tick();` (122) — 즉시 1회
  4. `setInterval(tick, 1000);` (123) — 1초마다
- **호출하는 함수**: `pad` (util.js)
- **호출자**: Header.init
- **올바름 검증**:
  - ✅ 즉시 1회 + 1초 간격 — 사용자가 페이지 진입 시 시계 즉시 표시.
  - ❌ **setInterval id 저장 안 함** — 페이지 SPA 전환 시 정리 불가. multi-page 기준이라 영향 미미. SPA 시점에 누수.
  - ⚠️ **clockEl null 시 tick 내부에서 return하지만 setInterval은 계속** — 무의미한 호출 1초마다. 사소.
  - 💡 `pad`가 util.js 글로벌이라는 의존 — 로드 순서 보장 필요.

#### `Header.updateLastUpdated()` (layout.js:126-130)
- **시그니처**: `() => void`
- **역할**: '최종 갱신 시각' 라벨 갱신
- **단계별 동작**:
  1. `const el = document.getElementById('lastUpdate'); if (!el) return;` (127-128)
  2. `el.textContent = nowDateLabel();` (129)
- **올바름 검증**:
  - ✅ DOM 부재 가드. textContent 안전.

#### `Header.handleRefresh()` async (layout.js:133-162)
- **시그니처**: `async () => void`
- **역할**: 새로고침 API 호출 + 이벤트 패널 재조회 + admin_url 동적 노출
- **단계별 동작**:
  1. `if (this.isRefreshing) return;` (134) — debounce
  2. `this.isRefreshing = true;` (135)
  3. `btn classList.add('spinning')` (136-137)
  4. **try** (138-150):
     - `Auth.apiFetch('/dashboard/api/refresh/')` (139)
     - `if (res.status === 401) { Auth.redirectLogin(); return; }` (140) — apiFetch 내부에서도 처리하지만 명시적 return으로 finally 진행
     - `data = await res.json()` (141)
     - `if (data.admin_url) { adminUrl = ...; showBtn }` (142-146)
     - `this.updateLastUpdated()` (147)
     - `if (typeof EventPanel !== 'undefined') EventPanel.loadEventList()` (149)
  5. **catch** (150-156):
     - `btn` 색상 빨강 + tooltip 변경
     - `setTimeout(() => { 복원 }, 3000)`
  6. **finally** (158-161):
     - `isRefreshing = false`
     - btn에서 'spinning' 제거
- **호출하는 함수**: `Auth.apiFetch`, `Auth.redirectLogin`, `Header.updateLastUpdated`, `EventPanel.loadEventList`, `setTimeout`
- **호출자**: 새로고침 버튼 클릭 (Header.init), Header.handleHome (대시보드일 때)
- **올바름 검증**:
  - ✅ **debounce + try-catch-finally + UI 피드백** — 매우 잘 짜여진 패턴.
  - ✅ EventPanel 부재 가드 — 비대시보드 페이지에서도 동작.
  - ⚠️ **401 분기 후 finally 실행** (R2 in 01과 같은 패턴) — redirectLogin 후 isRefreshing=false + spinning 제거가 잠시 실행됨. 페이지 이동되니 영향 미미.
  - ⚠️ **catch에서 btn null 가드 + setTimeout으로 복원** — 그러나 사용자가 3초 안에 새로고침을 또 누르면 isRefreshing=false 상태인데도 visual 충돌. setTimeout이 isRefreshing과 별도 동작하는 race.
  - ⚠️ **`(btn) btn.style.color = ''`** (155) — 인라인 style 직접 조작. CSS class로 분리 권장.
  - 💡 `EventPanel`은 글로벌 의존 — dashboard/panels/event-panel.js가 정의. 다음 sprint 영향.
  - 💡 setTimeout id 저장 안 함 — 빠른 연속 실패 시 timer 누적.

#### `Header.handleHome()` (layout.js:165-168)
- **시그니처**: `() => void`
- **역할**: 대시보드면 새로고침, 아니면 대시보드로 이동
- **단계별 동작**:
  1. `if (window.location.pathname === '/dashboard/')` → `this.handleRefresh()`
  2. else → `window.location.href = '/dashboard/'`
- **올바름 검증**:
  - ✅ 정상.
  - ⚠️ **path 정확 매칭** — `/dashboard/profile/`도 dashboard 하위인데 매칭 안 됨. 의도일 수 있음.

#### `Header.handleAdmin()` (layout.js:170)
- **시그니처**: `() => void`
- **역할**: 관리자 페이지로 이동
- **단계별 동작**:
  1. `window.location.href = this.adminUrl || '/admin-panel/accounts-management/';`
- **올바름 검증**:
  - ✅ fallback URL 안전.
  - 💡 매직스트링 — settings.ADMIN_BACKOFFICE_URL과 동일해야 정합. 백엔드 변경 시 어긋남 가능.

#### `Header.initLogout()` (layout.js:172-195)
- **시그니처**: `() => void`
- **역할**: 로그아웃 모달 + 확인/취소/성공 모달 흐름 + backdrop 클릭 닫기
- (01 도메인에서 상세 분석 — 이 파일에서는 위치만 명시)
- **올바름 검증**: (01의 분석 참조)

#### `Header.renderUser(username, role)` (layout.js:197-208)
- **시그니처**: `(username: string, role: string) => void`
- **역할**: 헤더에 이름·역할 라벨 렌더
- **단계별 동작**:
  1. `nameEl = getElementById('headerUsername')`, `roleEl = ...`
  2. `roleLabel = { worker:'작업자', facility_admin:'공장관리자', super_admin:'슈퍼관리자', viewer:'열람자' }`
  3. `nameEl.textContent = username ? '${username}님 환영합니다' : '-'`
  4. `roleEl.textContent = roleLabel[role] || '-'`
- **올바름 검증**:
  - ✅ textContent 안전.
  - ✅ DOM 부재 가드 (`if (nameEl)`).
  - ⚠️ `roleLabel[role]` 미정의 키 시 `'-'` — silent fallback. 새 role 추가 시 발견 늦음.
  - 💡 `roleLabel`이 함수 내 정의 — 호출마다 재생성. 모듈 상수로 빼면 미세 최적화.

#### `Header.showAdminBtn(role)` (layout.js:210-215)
- **시그니처**: `(role: string) => void`
- **역할**: 관리자 권한이면 어드민 버튼 노출
- **단계별 동작**:
  1. `if (role === 'facility_admin' || role === 'super_admin')`
  2. btn DOM의 `display = ''` (CSS default)
- **올바름 검증**:
  - ✅ 단순.
  - 💡 매직스트링 — UserType 상수와 일치해야 함 (Auth.role 백엔드에서 옴).
  - 💡 `display = ''`로 CSS default 복원 — 좋은 패턴 ('block' 등 하드코드 안 함).

#### `Header.init()` (layout.js:217-223)
- **시그니처**: `() => void`
- **역할**: 시계 시작 + 로그아웃 모달 + 5개 버튼 바인딩
- **단계별 동작**:
  1. `this.initClock();`
  2. `this.initLogout();`
  3. `btnRefresh, btnHome, btnAdmin` 바인딩 (옵셔널 체이닝)
- **올바름 검증**:
  - ✅ 모든 바인딩에 `?.` — DOM 부재 안전.
  - 💡 `btnLogout`은 initLogout 내부에서 바인딩 — 일관성을 위해 init 내부로 옮기는 것도 고려 가능.

### 3.4 [shared/layout.js](../../../drf-server/static/js/shared/layout.js) — `initHeaderAndSNB` (layout.js:232-251)

#### `initHeaderAndSNB()` async (layout.js:232-251)
- **시그니처**: `async () => User | null`
- **역할**: 페이지 진입 시 인증 확인 + 헤더·SNB 초기화 + user 객체 반환
- **단계별 동작**:
  1. `if (!Auth.getAccessToken()) { Auth.redirectLogin(); return null; }` (233)
  2. `const user = await Auth.getMe();` (235) — /api/auth/me/
  3. **if !user** (236-238):
     - `Header.renderUser(Auth.getUsername() || '-')` — localStorage 캐시 사용
     - `Menu.showError()` — "메뉴 로드 실패"
  4. **else** (239-245):
     - `Header.renderUser(user.username, user.role)`
     - `Header.showAdminBtn(user.role)`
     - `Menu.render(user.menu_tree)`
     - `if (user.admin_url) Header.adminUrl = user.admin_url`
     - `Auth.setRole(user.role)`
  5. `SNB.init();` (247)
  6. `Header.init();` (248)
  7. `Header.updateLastUpdated();` (249)
  8. `return user;` (250)
- **호출하는 함수**: `Auth.getAccessToken`, `Auth.redirectLogin`, `Auth.getMe`, `Auth.getUsername`, `Auth.setRole`, `Header.renderUser/showAdminBtn/init/updateLastUpdated`, `Menu.render/showError`, `SNB.init`
- **호출자**: app-sub.js, dashboard/app.js
- **올바름 검증**:
  - ✅ 토큰 부재 시 즉시 redirect — 정상 진입 가드.
  - ❌ **getMe 실패 시 헤더만 부분 동작** (이전 리뷰 08 H8) — Header.renderUser는 호출되어 헤더 상태는 정상 보임, 그런데 메뉴는 에러 표시. 사용자는 "왜 헤더는 멀쩡한데 메뉴만 깨졌나?" 혼란. 명시적 에러 페이지 또는 강제 로그아웃 권장.
  - ⚠️ **`Header.renderUser(Auth.getUsername() || '-')`** — role 인자 누락. roleEl이 `undefined` → `roleLabel[undefined]` → `'-'`. 정상 동작이지만 명시 호출 권장: `Header.renderUser(Auth.getUsername(), Auth.getRole())`.
  - ⚠️ **순서 의존성** (예: SNB.init 전에 SNB.drawer 사용) — DOM이 이 시점에 모두 존재해야 함. layout.js 로드 시점이 중요 (3.1의 NPE 위험).
  - 💡 **return user**가 호출자에게 유용 — app.js가 user.role 등 활용 가능.
  - 💡 `return user;`가 user=null 분기에서도 적용 — `if !user`가 return null 안 함. 호출자가 user를 사용하면 문제.

## 4. 종합 평가

### 강점
- ✅ **모듈 객체 패턴 (SNB, Menu, Header)으로 책임 분리** — 작은 객체 다수.
- ✅ **handleRefresh의 try-catch-finally + debounce** — 매우 잘 작성된 비동기 핸들러.
- ✅ **textContent 사용 (renderUser, updateLastUpdated)** — XSS 안전.
- ✅ **`?.` 옵셔널 체이닝** — Header/SNB의 init에서 일관 사용.
- ✅ **role 라벨 매핑** — 한글 라벨 분리.
- ✅ **`isRefreshing`, `_inited` 같은 상태 플래그로 idempotent**.

### 약점
- ❌ **Menu.render의 innerHTML 패턴** — XSS 위험 (현재 안전, 미래 위험).
- ❌ **getMe 실패 시 부분 동작 UI** — 사용자 혼란.
- ❌ **SNB의 모듈 로드 시점 getElementById** — layout.js 로드 위치에 따라 NPE.
- ⚠️ **iconMap 인라인 SVG + silent fallback** — 디자인 깨짐 발견 늦음.
- ⚠️ **roleLabel 미정의 silent fallback** — 새 role 추가 시.
- ⚠️ **handleRefresh의 setTimeout id 미저장** — 빠른 연속 실패 시 timer 누적.
- ⚠️ **menuTree·child 키 검증 부재** — 백엔드 응답 형식 변경 시 NPE.

### 중복 / 누락
- 📌 `Header.handleAdmin`의 fallback URL `/admin-panel/accounts-management/`이 settings.ADMIN_BACKOFFICE_URL과 일치해야 함 — 정책 동기화 필요.
- 📌 SVG 아이콘 인라인 — 이전 리뷰 08 H4 (sprite 분리).
- 📌 logout/refresh 모달 패턴이 my_profile.js와 유사 (이전 리뷰 01 R3).

### contract 정합성
- ✅ Auth.getMe 응답 형식 (id, username, role, menu_tree, admin_url) 사용.
- ⚠️ menu_tree 형식 검증 부재 — 백엔드 변경 영향 큼.
- ⚠️ role 값이 백엔드 UserType enum과 정확히 일치해야 함.

## 5. 리팩토링 권고

### R1. Menu.render innerHTML → createElement 패턴 [상 · 중]
- **왜 필요?**: XSS 패턴 정착 부족. 현재 안전(menu.label 등이 백엔드 데이터)이지만, 향후 사용자 데이터 추가 시 즉시 위험. 백엔드 응답이 마크업 포함하면 HTML 주입 가능.
- **장점**: XSS 자동 방지 / 패턴 정착.
- **단점**: 코드 길이 증가 (~30%). 가독성 약간 저하 — 빌더 패턴으로 보강 가능.
- **변경 위치**: [layout.js:50-95 Menu.render](../../../drf-server/static/js/shared/layout.js#L40-L100)
- **변경 예시**:
  ```js
  // before
  btn.innerHTML = `
    <span class="menu-icon">${icon}</span>
    <span class="menu-label">${menu.label}</span>
    ${hasChildren ? '<span class="menu-arrow">▶</span>' : ''}
  `;

  // after
  const iconSpan = document.createElement('span');
  iconSpan.className = 'menu-icon';
  iconSpan.innerHTML = icon;  // SVG는 의도된 마크업 — sprite 도입 시 createElementNS('svg')로 안전화
  const labelSpan = document.createElement('span');
  labelSpan.className = 'menu-label';
  labelSpan.textContent = menu.label;  // 사용자 데이터 안전 처리
  btn.appendChild(iconSpan);
  btn.appendChild(labelSpan);
  if (hasChildren) {
    const arrow = document.createElement('span');
    arrow.className = 'menu-arrow';
    arrow.textContent = '▶';
    btn.appendChild(arrow);
  }

  // child <a> 동일하게:
  // before
  subLi.innerHTML = `<a href="${child.path}" class="${isActive ? 'active' : ''}" data-path="${child.path}">${child.label}</a>`;

  // after
  const a = document.createElement('a');
  a.href = child.path;          // path 검증은 별도 (R5)
  if (isActive) a.classList.add('active');
  a.dataset.path = child.path;
  a.textContent = child.label;
  subLi.appendChild(a);
  ```

### R2. initHeaderAndSNB getMe 실패 시 명시적 처리 [상 · 소]
- **왜 필요?**: 부분 동작 UI는 사용자 혼란 + 보안 경계 약함. 인증된 사용자 정보를 못 받으면 미인증 상태로 처리.
- **장점**: 명확한 인증 경계.
- **단점**: getMe가 일시적 네트워크 에러로 실패할 때 강제 로그아웃은 가혹 — retry 옵션 필요.
- **변경 위치**: [layout.js:235-245](../../../drf-server/static/js/shared/layout.js#L235-L245)
- **변경 예시**:
  ```js
  // before
  const user = await Auth.getMe();
  if (!user) {
    Header.renderUser(Auth.getUsername() || '-');
    Menu.showError();
  } else { ... }

  // after — 옵션 A: 강제 재로그인
  const user = await Auth.getMe();
  if (!user) {
    console.warn('[layout] getMe failed, forcing relogin');
    Auth.redirectLogin();
    return null;
  }

  // after — 옵션 B: retry 1회 후 재로그인
  let user = await Auth.getMe();
  if (!user) {
    await new Promise(r => setTimeout(r, 1000));
    user = await Auth.getMe();
    if (!user) { Auth.redirectLogin(); return null; }
  }
  ```

### R3. SVG 아이콘 sprite 분리 [중 · 중]
- **왜 필요?**: 인라인 SVG는 추가·수정 시 layout.js 변경 + 디자이너 협업 어려움.
- **장점**: 디자인 도구 export 직접 / 캐시·재사용.
- **단점**: 빌드 도구 또는 정적 sprite 파일 도입 필요.
- **변경 위치**: 신규 [static/img/icons.svg](../../../drf-server/static/img/) sprite, [layout.js:33-37 iconMap](../../../drf-server/static/js/shared/layout.js#L33-L37)
- **변경 예시**:
  ```html
  <!-- static/img/icons.svg -->
  <svg xmlns="http://www.w3.org/2000/svg" style="display:none">
    <symbol id="icon-shield" viewBox="0 0 24 24"><path d="..."/></symbol>
    <symbol id="icon-monitor" viewBox="0 0 24 24"><path d="..."/></symbol>
    <symbol id="icon-settings" viewBox="0 0 24 24"><path d="..."/></symbol>
  </svg>
  ```
  ```js
  // layout.js
  const iconMap = { shield: 'icon-shield', monitor: 'icon-monitor', settings: 'icon-settings' };

  function createIconElement(key) {
    const id = iconMap[key];
    if (!id) {
      console.warn('[Menu] unknown icon:', key);
      return document.createTextNode('•');
    }
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', 15);
    svg.setAttribute('height', 15);
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `#${id}`);
    svg.appendChild(use);
    return svg;
  }
  ```

### R4. iconMap 미정의 console.warn [중 · 소]
- **왜 필요?**: silent `'•'` 폴백은 디자인 깨짐 발견 늦음.
- **장점**: 1초만에 원인 파악.
- **변경 위치**: [layout.js:54](../../../drf-server/static/js/shared/layout.js#L54)
- **변경 예시**:
  ```js
  let icon = this.iconMap[menu.icon];
  if (!icon) {
    console.warn('[Menu] icon not defined:', menu.icon);
    icon = '•';
  }
  ```

### R5. menuTree·child path 검증 [중 · 소]
- **왜 필요?**: 백엔드 응답 검증 부재 → NPE 또는 javascript: URL 주입 가능.
- **장점**: 방어적 코딩 / 보안 강화.
- **변경 위치**: [layout.js:50-95 forEach 내부](../../../drf-server/static/js/shared/layout.js#L50-L95)
- **변경 예시**:
  ```js
  function _isValidPath(p) {
    return typeof p === 'string' && (p.startsWith('/') || p.startsWith('http'));
  }
  function _isValidLabel(l) {
    return typeof l === 'string' && l.length > 0;
  }

  menuTree.forEach((menu) => {
    if (!_isValidLabel(menu.label) || !Number.isInteger(menu.id)) {
      console.warn('[Menu] invalid menu node:', menu);
      return;  // skip invalid
    }
    // ... 기존 렌더 로직 with createElement (R1)
    menu.children.forEach((child) => {
      if (!_isValidPath(child.path) || !_isValidLabel(child.label)) {
        console.warn('[Menu] invalid child:', child);
        return;
      }
      // ...
    });
  });
  ```

### R6. SNB DOM 참조를 init 시점으로 [중 · 소]
- **왜 필요?**: 모듈 로드 시점 getElementById는 head 로드 시 NPE 위험. 일관성을 위해 init에서 캐시.
- **장점**: 로드 위치 무관 / DOMContentLoaded 보장.
- **단점**: open/close가 init 호출 전에 호출되면 NPE. 단, 호출자(initHeaderAndSNB)가 SNB.init을 명시 호출 — OK.
- **변경 위치**: [layout.js:12-24](../../../drf-server/static/js/shared/layout.js#L12-L24)
- **변경 예시**:
  ```js
  const SNB = {
    drawer:  null,
    overlay: null,
    open()   { this.drawer?.classList.add('open'); this.overlay?.classList.add('open'); },
    close()  { this.drawer?.classList.remove('open'); this.overlay?.classList.remove('open'); },
    toggle() { (this.drawer?.classList.contains('open')) ? this.close() : this.open(); },
    init() {
      this.drawer  = document.getElementById('snbDrawer');
      this.overlay = document.getElementById('snbOverlay');
      document.getElementById('hamburger')?.addEventListener('click', () => this.toggle());
      this.overlay?.addEventListener('click', () => this.close());
    },
  };
  ```

### R7. roleLabel 모듈 상수화 + 미정의 console.warn [중 · 소]
- **왜 필요?**: renderUser 호출마다 객체 재생성. 새 role 추가 시 silent fallback.
- **변경 위치**: [layout.js:200-208](../../../drf-server/static/js/shared/layout.js#L197-L208)
- **변경 예시**:
  ```js
  // 모듈 상단
  const ROLE_LABEL = Object.freeze({
    worker: '작업자',
    facility_admin: '공장관리자',
    super_admin: '슈퍼관리자',
    viewer: '열람자',
  });

  // renderUser 내부
  renderUser(username, role) {
    const nameEl = document.getElementById('headerUsername');
    const roleEl = document.getElementById('headerRole');
    if (nameEl) nameEl.textContent = username ? `${username}님 환영합니다` : '-';
    if (roleEl) {
      const label = ROLE_LABEL[role];
      if (!label && role) console.warn('[Header] unknown role:', role);
      roleEl.textContent = label || '-';
    }
  },
  ```

### R8. handleRefresh setTimeout 누적 방지 [하 · 소]
- **왜 필요?**: 빠른 연속 실패 시 timer 누적 → 빨간 색·tooltip 복원 시점 어긋남.
- **변경 위치**: [layout.js:151-156](../../../drf-server/static/js/shared/layout.js#L151-L156)
- **변경 예시**:
  ```js
  Header._refreshErrTimer = null,
  // catch 내부
  if (btn) {
    btn.style.color = 'var(--danger)';
    btn.title = '새로고침 실패 — 잠시 후 다시 시도하세요';
    clearTimeout(Header._refreshErrTimer);
    Header._refreshErrTimer = setTimeout(() => {
      btn.style.color = ''; btn.title = '새로고침';
    }, 3000);
  }
  ```

### R9. initHeaderAndSNB의 renderUser 인자 명시 [하 · 소]
- **왜 필요?**: getMe 실패 시 role 인자 누락 → roleEl이 `'-'`. 의도 명확화.
- **변경 위치**: [layout.js:237](../../../drf-server/static/js/shared/layout.js#L237)
- **변경 예시**:
  ```js
  // before
  Header.renderUser(Auth.getUsername() || '-');
  // after
  Header.renderUser(Auth.getUsername() || '-', Auth.getRole() || null);
  ```

### R10. Header.handleAdmin URL 백엔드 동기화 [하 · 소]
- **왜 필요?**: settings.ADMIN_BACKOFFICE_URL과 클라이언트 fallback 일치 필요. 백엔드 변경 시 어긋남.
- **변경 위치**: [layout.js:170](../../../drf-server/static/js/shared/layout.js#L170)
- **변경 예시**:
  ```js
  // 더 안전: adminUrl이 항상 설정되어 있도록 initHeaderAndSNB에서 보장
  // 또는 app_config.html에 ADMIN_URL 주입
  ```

## 6. 단계별 적용 순서

### 1단계 — 즉시 (1일) ⚡
- **R4** iconMap console.warn — 1줄.
- **R7** roleLabel 상수화 + console.warn — 모듈 상단 5줄.
- **R8** setTimeout 누적 방지 — 1 변수 추가.
- **R9** renderUser 인자 명시 — 1줄.
- **이유**: 모두 작은 변경, 가시성 향상.

### 2단계 — 1주 내 🔧
- **R1** Menu.render innerHTML → createElement (XSS 패턴 정착)
- **R5** menuTree·path 검증
- **R6** SNB DOM 참조 init 시점으로
- **R2** initHeaderAndSNB 실패 명시적 처리 (운영 정책 합의 후 옵션 A 또는 B)
- **이유**: 보안·안정성 핵심. R1은 약간 큰 작업이지만 패턴 정착.

### 3단계 — 다음 sprint 🏗
- **R3** SVG sprite 분리 (디자이너 협업)
- **R10** admin URL 백엔드 동기화 (정책 결정)

### ⚠️ 주의사항 (초보자용)

- **R1 createElement 적용 시 SVG 마크업 처리 신중**: SVG는 HTML과 namespace 다름. `createElementNS('http://www.w3.org/2000/svg', 'svg')` 필요. innerHTML에 SVG string은 작동하지만 createElement('svg')는 의도대로 안 됨. R3과 함께 진행 권장.
- **R2 강제 로그아웃은 사용자 경험 영향 큼**: 일시적 네트워크 에러로도 로그아웃되면 UX 악화. 옵션 B(retry 1회) 권장. 운영 모니터링 후 정책 조정.
- **R3 SVG sprite는 CSS-in-JS 환경 호환성 확인**: `<use href="#icon-x">` 사용 시 같은 페이지에 sprite SVG가 로드되어 있어야 함. base.html에 `<svg style="display:none"><use>...` 또는 외부 파일 reference.
- **R6 SNB DOM init 시점 변경 시 호출 순서 보장**: SNB.open/close가 SNB.init 호출 전에 사용되면 NPE. 현재 호출 순서(initHeaderAndSNB → SNB.init → 사용자 인터랙션) 안전하지만, 다른 코드에서 호출하지 않는지 grep.
- **모든 변경 후 페이지 진입 4종 시나리오 검증**: 1) 정상 로그인 후 진입 / 2) 토큰 만료 후 진입 / 3) 메뉴 트리 빈 응답 / 4) 네트워크 에러. 모달·SNB·헤더 동작 각각 확인.
