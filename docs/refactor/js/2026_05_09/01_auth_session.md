# 01. 인증·세션 (Auth · Login · Logout · Password Change)

## 1. 관련 파일 및 의존성

### 1.1 파일 목록
- [drf-server/static/js/shared/auth.js](../../../drf-server/static/js/shared/auth.js) — 110줄, **`Auth` 객체 (15개 메서드)**
- [drf-server/static/js/auth/login.js](../../../drf-server/static/js/auth/login.js) — 156줄, **로그인 폼 IIFE**
- [drf-server/static/js/detail/my_profile.js](../../../drf-server/static/js/detail/my_profile.js) — 232줄, **`PasswordModal` 객체 (11개 메서드)** + `loadProfile` (06에서 다룸)
- [drf-server/static/js/shared/layout.js:172-195](../../../drf-server/static/js/shared/layout.js#L172) — **`Header.initLogout` 메서드** (전체 분석은 04에서)
- [drf-server/templates/auth/login.html](../../../drf-server/templates/auth/login.html) — 로그인 페이지 마크업

### 1.2 의존성 그래프
```
config.js (AppConfig)
    │
    ▼
auth.js (Auth) ────────────┐
    ▲                      │
    │                      ▼
    │             login.js / my_profile.js / layout.js
    │             (Auth.apiFetch, getAccessToken, setTokens, redirectLogin 사용)
    │
    └── 백엔드 contract: POST /api/auth/login/, /me/, /token/refresh/, /logout/, /password/change/, /profile/
```

### 1.3 호출자 인벤토리 (grep 결과)
- `Auth.apiFetch` 사용처: layout.js (refresh, logout), my_profile.js (profile, password), 모든 admin/* 페이지, login.js (me)
- `Auth.getAccessToken`: login.js, layout.js, ws-client.js (attachToken)
- `Auth.getMe`: layout.js, worker-ws.js, admin/main.js
- `Auth.setTokens`: login.js만
- `Auth.redirectLogin`: layout.js, my_profile.js, admin/main.js

## 2. 기능 흐름

### 2.1 로그인 → 토큰 발급 → 대시보드 진입
```
사용자 → /accounts/login/ 페이지
    │
    ▼ DOMContentLoaded
login.js IIFE 시작
    │
    ├─ Auth.getAccessToken() 존재?
    │   ├─ Yes → Auth.apiFetch('/api/auth/me/')
    │   │   ├─ 200 → window.location = '/dashboard/'
    │   │   └─ 4xx → Auth.clear() (토큰 정리)
    │   └─ No → 폼 노출
    │
    ▼ 사용자 submit
form.submit 핸들러
    ├─ validateUsername / validatePassword (클라 검증)
    ├─ fetch POST /api/auth/login/ {username, password}
    │   ├─ ok → Auth.setTokens({access, refresh, username, role})
    │   │     window.location = '/dashboard/'
    │   └─ !ok → showServerError(data.error)
```

### 2.2 인증된 API 호출 + 자동 refresh
```
모든 페이지 → Auth.apiFetch(url, opts)
    │
    ├─ _resolveUrl(url): AppConfig.apiUrl 우선
    ├─ Authorization: Bearer <access_token> 부착
    ├─ fetch(finalUrl, {...opts, headers})
    │
    └─ res.status === 401?
        ├─ _refresh() 시도
        │   ├─ POST /api/auth/token/refresh/ {refresh}
        │   ├─ ok → localStorage.access_token 갱신, return true
        │   └─ !ok → return false
        ├─ refreshed: 헤더 갱신 후 fetch 재시도
        │   └─ 또 401 → redirectLogin()
        └─ 성공: 그대로 res 반환
```

### 2.3 비밀번호 변경
```
사용자 → /dashboard/profile/ → "비밀번호 변경" 클릭
    │
    ▼ PasswordModal.open()
모달 노출, 현재/신규/신규확인 입력
    │
    ├─ blur 시: _validateCurrent / _validateNew / _validateConfirm
    └─ submit:
        ├─ 3개 검증 모두 통과 → btn.disabled = true
        ├─ Auth.apiFetch POST /api/auth/password/change/ {current, new, new_confirm}
        ├─ 응답:
        │   ├─ 401 → redirectLogin
        │   ├─ ok → close + successModal 노출
        │   └─ 4xx → 필드별 에러 표시
        └─ finally: btn.disabled = false
```

### 2.4 로그아웃
```
사용자 → 헤더 로그아웃 버튼
    │
    ▼ Header.initLogout 핸들러
modal.style.display = 'flex' (확인 모달)
    │
    ▼ 확인 클릭
Auth.apiFetch POST /api/auth/logout/
    │
    └─ finally:
        ├─ modal close
        ├─ successModal show
        └─ 사용자 OK 클릭 → Auth.redirectLogin()
            └─ Auth.clear() + window.location = '/accounts/login/'
```

## 3. 함수 분석

### 3.1 [shared/auth.js](../../../drf-server/static/js/shared/auth.js) — `Auth` 객체

#### `Auth.getAccessToken()`
- **시그니처**: `() => string | null`
- **역할**: localStorage에서 access_token 조회
- **단계별 동작**:
  1. `localStorage.getItem('access_token')` 반환
- **호출하는 함수**: 없음 (localStorage 직접)
- **호출자**: login.js (페이지 진입 시 체크), layout.js (initHeaderAndSNB), ws-client.js (attachToken)
- **올바름 검증**:
  - ✅ 단순·정확. localStorage 반환은 `null` 또는 string.
  - 💡 토큰 유효성(만료) 검증은 안 함 — 만료된 토큰도 반환 → 호출자가 _refresh 트리거. 의도된 설계.

#### `Auth.getRefreshToken()`, `Auth.getRole()`, `Auth.getUsername()`
- **시그니처**: 모두 `() => string | null`
- **역할**: localStorage에서 각각 refresh_token / role / username 조회
- **올바름 검증**:
  - ✅ 단순. getter 패턴.
  - 💡 4개 메서드가 같은 패턴 — `Auth._get(key)` 헬퍼로 압축 가능 (사소).

#### `Auth.setTokens({ access, refresh, username, role } = {})`
- **시그니처**: `(payload?: {access?, refresh?, username?, role?}) => void`
- **역할**: localStorage에 토큰 4종 저장 (각각 truthy/undefined 체크)
- **단계별 동작**:
  1. `access` truthy면 setItem
  2. `refresh` truthy면 setItem
  3. `username !== undefined`면 setItem (`?? ''` 폴백)
  4. `role !== undefined`면 setItem (`?? ''` 폴백)
- **호출하는 함수**: 없음
- **호출자**: login.js (로그인 성공 시 1회)
- **올바름 검증**:
  - ✅ access/refresh는 truthy 체크, username/role은 `undefined` 체크 — 의도 명확 (빈 문자열도 저장 가능).
  - ⚠️ default `{}` 파라미터로 호출 시 모두 undefined → 아무것도 저장 안 함. 의도된 동작이지만 안전장치 부재 (잘못된 호출 시 silent skip).
  - 💡 `setRole` 메서드와 일부 책임 중복.

#### `Auth.setRole(role)`
- **시그니처**: `(role: string) => void`
- **역할**: localStorage role만 갱신
- **단계별 동작**:
  1. `localStorage.setItem('role', role ?? '')`
- **호출자**: layout.js (initHeaderAndSNB의 user 정보 받은 후), admin/main.js
- **올바름 검증**:
  - ✅ 단순. setTokens와 책임 분리는 OK (login 외 시점에서 role만 갱신 필요).

#### `Auth.clear()`
- **시그니처**: `() => void`
- **역할**: localStorage의 4개 토큰/정보 제거
- **단계별 동작**:
  1. removeItem 4번 (access, refresh, username, role)
- **호출자**: redirectLogin (내부), login.js (토큰 무효 시), admin/main.js
- **올바름 검증**:
  - ✅ 정상.
  - 💡 키 목록이 setTokens와 별도 — 추후 키 추가 시 한쪽 누락 가능. 키 배열 상수화 가능.

#### `Auth._resolveUrl(url)`
- **시그니처**: `(url: string) => string`
- **역할**: AppConfig.apiUrl 사용 가능하면 사용, 아니면 url 그대로
- **단계별 동작**:
  1. `window.AppConfig?.apiUrl` 함수 존재 체크
  2. 있으면 `apiUrl(url)` 호출 결과 반환
  3. 없으면 url 그대로
- **호출자**: apiFetch, _refresh 내부
- **올바름 검증**:
  - ✅ AppConfig 부재 fallback 안전.
  - ⚠️ AppConfig 미정의 시 silent fallback — config.js가 로드 실패하면 디버깅 어려움. `console.warn` 한 줄 권장.

#### `Auth._refresh()`
- **시그니처**: `async () => boolean`
- **역할**: refresh_token으로 새 access_token 발급 → localStorage 갱신
- **단계별 동작**:
  1. `getRefreshToken()` 조회, 없으면 false
  2. `fetch(_resolveUrl('/api/auth/token/refresh/'), POST, {refresh})`
  3. `!res.ok` → false
  4. ok → `data.access`를 localStorage에 setItem, true
  5. catch → false
- **호출자**: apiFetch (401 응답 시 자동)
- **올바름 검증**:
  - ✅ 응답 검증·에러 처리·Promise 반환 모두 정상.
  - ❌ **동시성 미보호** — 동시에 여러 fetch가 401을 받으면 _refresh가 다발로 호출됨. 백엔드가 ROTATE_REFRESH_TOKENS 도입 시 마지막 refresh만 유효 → 앞선 요청들이 무효화된 토큰으로 재시도 → 강제 로그아웃 가능. **싱글톤 in-flight Promise 가드 필요** (이전 리뷰 01 A3와 동일).
  - 💡 `data.refresh` 갱신은 안 함 — refresh 자체는 회전(rotation) 미사용 가정. 백엔드 정책에 따라.

#### `Auth.apiFetch(url, opts = {})`
- **시그니처**: `async (url: string, opts?: RequestInit) => Response`
- **역할**: 인증 헤더 자동 부착 + 401 시 1회 refresh 재시도 + 또 401이면 로그인 리다이렉트
- **단계별 동작**:
  1. `_resolveUrl(url)`
  2. `getAccessToken()` 있으면 `Authorization: Bearer ...` 헤더 부착
  3. `Content-Type: application/json` 기본
  4. `fetch(finalUrl, {...opts, headers})`
  5. `res.status === 401`?
     - `_refresh()` → true면 헤더 갱신 후 1회 재시도
     - 재시도도 401이면 `redirectLogin()` 호출하고 res 반환
  6. 그 외엔 res 그대로 반환
- **호출자**: 거의 모든 페이지 JS (40+ 호출 지점)
- **올바름 검증**:
  - ✅ 인증 헤더 자동·재시도·리다이렉트 흐름 명확.
  - ⚠️ **`opts.headers` 사용 시 Content-Type 의도치 않게 덮일 수 있음** — `Object.assign({Content-Type:...}, opts.headers)`이라 opts.headers의 Content-Type이 우선. opts에서 명시적으로 지정 안 하면 JSON 기본 적용. 정상 동작.
  - ⚠️ **POST이지만 body 없는 호출 시** — POST `/api/auth/logout/` 호출 시 layout.js가 body 없이 호출 → Content-Type: application/json만 있고 body 없음. 백엔드는 body를 안 읽으니 OK이지만 불필요 헤더.
  - ❌ **redirectLogin 후 res 반환** — 호출자가 res.status === 401를 한 번 더 체크하는 패턴(my_profile.js loadProfile)이 있는데, redirectLogin이 이미 호출되어 페이지 이동 진행 중. 호출자는 res를 받아 추가 처리 시도하지만 의미 없음. **silent하지만 두 번 redirectLogin 가능**.
  - 💡 _refresh 동시성 (위 ❌)와 결합되면 강제 로그아웃 빈도 ↑.

#### `Auth.getMe()`
- **시그니처**: `async () => object | null`
- **역할**: GET /api/auth/me/ 호출하여 사용자 정보 반환
- **단계별 동작**:
  1. `apiFetch('/api/auth/me/')`
  2. `!res.ok` → null
  3. ok → `await res.json()` 반환
  4. catch → null
- **호출자**: layout.js (initHeaderAndSNB), worker-ws.js (DOMContentLoaded), admin/main.js
- **올바름 검증**:
  - ✅ try-catch + null 반환 패턴 일관.
  - 💡 catch가 광범위(`catch {}`) — 어떤 에러였는지 모름. 디버깅 어려움. 적어도 console.warn.

#### `Auth.redirectLogin()`
- **시그니처**: `() => void`
- **역할**: 토큰 정리 후 로그인 페이지로 이동
- **단계별 동작**:
  1. `clear()` 호출
  2. `window.location.href = '/accounts/login/'`
- **호출자**: apiFetch (401 후 401), layout.js (Auth.getAccessToken 부재 시), my_profile.js (401 시), admin/main.js
- **올바름 검증**:
  - ✅ 단순.
  - ⚠️ 페이지 경로가 하드코드 — `/accounts/login/`. AppConfig에 노출하면 환경 분기 가능. 사소.
  - 💡 redirectLogin이 호출된 후에도 호출자 코드가 계속 실행될 수 있음 (브라우저가 navigation 시작하기 전 동기 코드 실행). 의도된 동작 — `return` 명시 권장.

### 3.2 [auth/login.js](../../../drf-server/static/js/auth/login.js) — 로그인 폼 IIFE

#### `(IIFE 진입)` 자동 리다이렉트 체크
- **시그니처**: 없음 (IIFE 본문)
- **역할**: 페이지 진입 시 토큰이 있으면 자동으로 대시보드 이동
- **단계별 동작**:
  1. `Auth.getAccessToken()` 체크
  2. 있으면 `Auth.apiFetch('/api/auth/me/').then`
  3. ok면 `/dashboard/`로 이동
  4. !ok면 `Auth.clear()`
  5. catch는 `() => {}` (no-op)
- **올바름 검증**:
  - ✅ 일관된 자동 리다이렉트.
  - ⚠️ catch가 `() => {}` — 네트워크 에러 시 사용자에게 피드백 없음. 그래도 폼은 그대로 노출되니 큰 문제 아님.
  - 💡 apiFetch가 401 시 redirectLogin을 자동 호출하는데, 여기서 또 `Auth.clear()` 호출 → 중복. apiFetch가 이미 처리하니 불필요. 단, 401이 아닌 4xx (예: 서버 에러)인 경우엔 의미 있음.

#### `syncClear(input, clearBtn)`
- **시그니처**: `(input: HTMLInputElement, clearBtn: HTMLElement) => void`
- **역할**: 입력값 길이에 따라 clear 버튼의 visible 클래스 토글
- **단계별 동작**:
  1. `clearBtn.classList.toggle('visible', input.value.length > 0)`
- **호출자**: input 이벤트 리스너
- **올바름 검증**:
  - ✅ 단순·정확.

#### `showFieldError(input, errorEl, msg)` / `clearFieldError(input, errorEl)`
- **시그니처**: `(input, errorEl, msg) => void` / `(input, errorEl) => void`
- **역할**: 필드별 에러 표시·해제 (input에 `error` 클래스 + 에러 div에 `show` 클래스)
- **올바름 검증**:
  - ✅ 정상.
  - 💡 다른 폼(비밀번호 변경)에도 동일 패턴 — `shared/form-errors.js` 추출 가능.

#### `showServerError(msg)` / `clearServerError()`
- **시그니처**: `(msg: string) => void` / `() => void`
- **역할**: 폼 상단 서버 에러 메시지
- **올바름 검증**:
  - ✅ 정상.

#### `validateUsername(val)` / `validatePassword(val)`
- **시그니처**: `(val: string) => string` (에러 메시지 또는 빈 문자열)
- **역할**: 클라이언트 사이드 입력 검증
- **단계별 동작**: (validatePassword 예)
  1. 빈 값 → required
  2. < 8자 → minLength
  3. 영문/숫자/특수 중 2종 미만 → pattern
  4. 통과 → ''
- **호출자**: blur 이벤트, submit 이벤트
- **올바름 검증**:
  - ✅ 정규식 정확. 백엔드 LoginSerializer.validate_password와 동일 정책.
  - ❌ **클라/서버 정책 듀얼 메인테넌스** — 백엔드 변경 시 silent 누락 위험 (이전 리뷰 01 A7 재확인).
  - 💡 빈 문자열 반환 vs `null` 반환 패턴 — 둘 중 하나 선택. 현재는 빈 문자열로 통일.

#### `form.addEventListener('submit', async (e) => {...})`
- **시그니처**: 이벤트 핸들러
- **역할**: 폼 검증 + 로그인 API 호출 + 성공 시 토큰 저장·리다이렉트
- **단계별 동작**:
  1. `e.preventDefault()`
  2. clearServerError
  3. validateUsername / validatePassword
  4. 한쪽이라도 에러면 return
  5. btn.disabled = true, "로그인 중..."
  6. fetch POST /api/auth/login/ (Auth.apiFetch가 아닌 fetch 직접 — 토큰 부재 시점이라 정상)
  7. !res.ok → showServerError
  8. ok → Auth.setTokens(...) → window.location = '/dashboard/'
  9. catch → showServerError("서버에 연결할 수 없습니다.")
  10. finally → btn 복원
- **올바름 검증**:
  - ✅ 흐름 명확. async/await 정확.
  - ✅ try-finally로 버튼 복원 — 좋은 패턴.
  - ⚠️ AppConfig.apiUrl 폴백 패턴 — 한 줄로 길게 표현됨. `Auth._resolveUrl`을 외부 노출하면 단순화 가능.
  - 💡 `data.error || MSG.server.authFail` — 401 응답이 `{error}` 봉투인데 백엔드에서 다른 형식으로 오면 fallback. OK.

### 3.3 [shared/layout.js](../../../drf-server/static/js/shared/layout.js) — `Header.initLogout` (로그아웃 부분만)

#### `Header.initLogout()`
- **시그니처**: `() => void`
- **역할**: 로그아웃 모달 + 확인/취소/성공 모달 흐름 + backdrop 클릭 닫기
- **단계별 동작**:
  1. modal·successModal·btn 4개 DOM 조회 (querySelector)
  2. btnLogout 클릭 → modal.display = 'flex'
  3. cancel 클릭 → modal close
  4. confirm 클릭 → try { apiFetch POST /api/auth/logout/ } finally { modal close + success 노출 }
  5. successOk 클릭 → Auth.redirectLogin
  6. backdrop 클릭(modal === e.target) → close
- **호출자**: Header.init() (initHeaderAndSNB)
- **올바름 검증**:
  - ✅ `try-finally` 패턴 — API 실패해도 UI 진행. 좋은 UX.
  - ⚠️ **API 실패 시도 success 모달 노출** — 사용자가 "성공"으로 인식. 의도일 수 있으나(JWT는 stateless라 클라이언트 기준 로그아웃 충분), 운영 측면에서 LoginLog 기록 누락. silent 실패.
  - ⚠️ **success 모달 backdrop 클릭은 close 안 됨** — modal만 backdrop 이벤트 등록. successModal은 OK 버튼만으로 닫힘. UX 일관성 부족.
  - 💡 모달 패턴이 my_profile.js의 PasswordModal과 유사 — `shared/modal.js` 베이스 가능.

### 3.4 [detail/my_profile.js](../../../drf-server/static/js/detail/my_profile.js) — `PasswordModal` 객체

> **참고**: my_profile.js의 `loadProfile`, `setField`, `formatPhone`은 페이지 진입(05) 또는 detail 페이지(09)에서 다룸. 여기는 `PasswordModal`만 인증 도메인으로 분석.

#### `PasswordModal.init()`
- **시그니처**: `() => void`
- **역할**: 모달 DOM 참조 캐싱 + 버튼·입력 이벤트 바인딩
- **단계별 동작**:
  1. modal·successModal DOM 참조
  2. inputs/clears/hints 3개 키(current/new/confirm) 매핑
  3. 4개 버튼에 click 핸들러 바인딩
  4. _bindField 3번 호출 (current/new/confirm)
- **호출자**: DOMContentLoaded
- **올바름 검증**:
  - ✅ 정확. 모든 DOM이 페이지에 존재한다는 가정 (`?.`로 일부만 안전).
  - ⚠️ **inputs/clears/hints는 `?.` 없이 직접 참조** — 페이지에 해당 DOM 없으면 init 시점에 null 저장 후 후속 메서드에서 NPE. 의도된 가정(페이지 전용 JS)이지만 방어적 가드 권장.

#### `PasswordModal._bindField(key)`
- **시그니처**: `(key: 'current'|'new'|'confirm') => void`
- **역할**: 한 필드의 input/blur/clear 이벤트 바인딩
- **단계별 동작**:
  1. `input.addEventListener('input', ...)` — clear 토글 + 에러 클리어 + 즉시 검증(strict=false)
  2. `input.addEventListener('blur', ...)` — strict=true 검증
  3. `clear.addEventListener('click', ...)` — value 비우기
- **호출자**: init 내부 3번
- **올바름 검증**:
  - ✅ strict=true(blur) vs strict=false(input)로 입력 중엔 관대, 떠날 때 엄격 — 좋은 UX.
  - ✅ 패턴화된 분기 — 명확.

#### `PasswordModal._validateCurrent() / _validateNew(strict) / _validateConfirm(strict)`
- **시그니처**: `() => boolean` / `(strict: boolean) => boolean` / 동
- **역할**: 각 필드 검증, 통과면 true / 실패면 _showError 호출 후 false
- **단계별 동작 (_validateNew)**:
  1. val 빈 값 + strict면 required 에러, return false
  2. 길이 8~16 외 또는 (영문/숫자/특수) < 2 → format 에러, return false
  3. _clearError + return true
- **호출자**: blur, submit
- **올바름 검증**:
  - ✅ 백엔드 PasswordChangeSerializer와 정책 일치 (8~16자 + 2종 이상).
  - ❌ **클라/서버 듀얼 메인테넌스** — login.js의 validatePassword와도 일부 다름 (login은 8자 이상, 여긴 8~16자). 두 정책이 정합한지 백엔드와 cross-check 필요.
  - 💡 strict=false로 호출 시 빈 값은 통과 — 즉시 검증에서 사용자 타이핑 중 에러 안 띄움. 좋은 UX.

#### `PasswordModal._showError(key, msg) / _clearError(key)`
- **시그니처**: `(key, msg) => void` / `(key) => void`
- **역할**: 필드 에러/힌트 텍스트 + 클래스 토글
- **올바름 검증**:
  - ✅ 정확. login.js와 동일 패턴 — 추출 가능 (R3).

#### `PasswordModal.open()`
- **시그니처**: `() => void`
- **역할**: 모든 필드 초기화 + 모달 노출 + current 필드 focus
- **단계별 동작**:
  1. 3개 키 forEach: input.value = '', clear.visible = false, _clearError
  2. modal.display = 'flex'
  3. inputs.current.focus()
- **올바름 검증**:
  - ✅ 매번 깨끗한 상태로 열림.
  - 💡 close()는 단순 `display = 'none'`만 — 다음 open이 초기화하므로 OK이지만 동시 모달이 있을 때 메모리 누수는 없음.

#### `PasswordModal.submit()`
- **시그니처**: `async () => void`
- **역할**: 검증 통과 시 비밀번호 변경 API 호출, 성공/실패 처리
- **단계별 동작**:
  1. 3개 검증 모두 호출 (strict=true)
  2. 한쪽이라도 false면 return
  3. btn.disabled = true
  4. try: apiFetch POST /api/auth/password/change/
  5. 401 → redirectLogin (return)
  6. !res.ok → 필드별 에러 (data.current_password / new_password / new_password_confirm 배열 첫 요소)
  7. ok → close + successModal 노출
  8. finally: btn.disabled = false
- **올바름 검증**:
  - ✅ try-finally 안전. 401 분기 OK.
  - ❌ **401 분기 후 finally가 실행되어 버튼 활성화 — 그러나 redirectLogin이 페이지 이동 트리거**. 이론상 finally가 페이지 이동 전에 실행되지만 빠른 navigation으로 사용자 인지 영향 없음. 다만 명시적으로 `return` 후 `finally` 실행되도록 보장.
  - ⚠️ **응답 형식 가정** — 백엔드 PasswordChangeSerializer가 `{current_password: ['msg']}` 배열로 응답. 백엔드가 dict나 string으로 응답 형식 변경 시 `data.current_password[0]`이 NPE. defensive coding 권장.
  - 💡 success 모달 backdrop 닫기 부재 — Header.initLogout과 동일 이슈.

## 4. 종합 평가

### 강점
- ✅ **Auth 객체의 단일 진입점 패턴** — apiFetch 한 곳에서 토큰·refresh·redirect 처리. 사용자 측 단순.
- ✅ **try-finally 패턴** — 버튼 복원·상태 정리에 일관 적용.
- ✅ **strict 매개변수로 input/blur 검증 분리** — 좋은 UX 패턴.
- ✅ **PasswordModal init/_bindField/_validateX 책임 분리** — 작지만 잘 정리된 객체.
- ✅ **`?` 옵셔널 체이닝 적극 활용** — 일부 DOM 부재에 안전.

### 약점
- ❌ **`Auth._refresh` 동시성 미보호** — 핵심 버그 가능성.
- ❌ **클라/서버 검증 정책 듀얼 메인테넌스 (3곳)** — login.js, my_profile.js, 백엔드.
- ⚠️ **localStorage 토큰 보관** — XSS 취약 (구조적 — 즉시 해결 어려움, 다층 방어 필요).
- ⚠️ **광범위 catch (`catch {}`)** — getMe, IIFE 등.

### 중복 패턴
- 폼 에러 표시 (`showFieldError` / `_showError`) — login.js, my_profile.js
- 모달 (logout, password) — open/close/backdrop 패턴
- AppConfig fallback (`Auth._resolveUrl`, login.js fetch 호출) — 동일 패턴

### contract 정합성
- ✅ 백엔드 LoginSerializer/PasswordChangeSerializer 응답 형식과 일치
- ⚠️ password 정책이 Login (8+) vs PasswordChange (8~16)로 다름 — 의도?

## 5. 리팩토링 권고

### R1. `Auth._refresh` 동시성 가드 (싱글톤 in-flight Promise) [상 · 소]
- **왜 필요?**: 동시 다발 401 시 _refresh가 여러 번 호출됨. 백엔드가 ROTATE_REFRESH_TOKENS 도입 시 마지막 refresh만 유효 → 앞선 fetch들이 무효 토큰으로 재시도 → 강제 로그아웃 회귀 버그.
- **장점**: 동시 요청 안전 / refresh 호출 1회로 최소화.
- **단점**: 거의 무비용 (1줄 패턴).
- **변경 위치**: [auth.js:48-65](../../../drf-server/static/js/shared/auth.js#L48-L65) `_refresh()` 진입.
- **변경 예시**:
  ```js
  // before
  async _refresh() {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return false;
    try { ... } catch { return false; }
  },

  // after
  _refreshing: null,
  async _refresh() {
    if (this._refreshing) return this._refreshing;
    this._refreshing = (async () => {
      const refreshToken = this.getRefreshToken();
      if (!refreshToken) return false;
      try {
        const res = await fetch(this._resolveUrl('/api/auth/token/refresh/'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh: refreshToken }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        localStorage.setItem('access_token', data.access);
        return true;
      } catch { return false; }
    })();
    try { return await this._refreshing; }
    finally { this._refreshing = null; }
  },
  ```

### R2. apiFetch의 redirectLogin 후 res 반환 명확화 [중 · 소]
- **왜 필요?**: 호출자가 res.status === 401 한 번 더 체크하는 패턴 발생 (my_profile.js loadProfile) → redirectLogin 두 번 호출.
- **장점**: 흐름 명확 / silent 중복 호출 차단.
- **단점**: 호출자 측 코드 패턴 변경 (작음).
- **변경 위치**: [auth.js:69-90](../../../drf-server/static/js/shared/auth.js#L69-L90)
- **변경 예시**:
  ```js
  // after — redirectLogin 호출 시 throw 또는 명시적 sentinel
  if (res.status === 401) {
    this.redirectLogin();
    throw new Error('UNAUTHENTICATED'); // 호출자 try-catch 또는 페이지 이동 진행
  }
  ```
  또는 호출자에서 `await res; if (res.status === 401) return;` 패턴 제거 (apiFetch가 처리).

### R3. 폼 에러 헬퍼 추출 [중 · 소]
- **왜 필요?**: login.js의 `showFieldError`/`clearFieldError`와 my_profile.js의 `_showError`/`_clearError`가 동일 패턴.
- **장점**: 변경 한 곳 / 새 폼 추가 시 import 한 줄.
- **단점**: 베이스 모듈 1개 추가.
- **변경 위치**: 신규 [shared/form-errors.js](../../../drf-server/static/js/shared/form-errors.js)
- **변경 예시**:
  ```js
  // shared/form-errors.js
  function showFieldError(input, errorEl, msg) {
    input.classList.add('error');
    errorEl.textContent = msg;
    errorEl.classList.add('show');
  }
  function clearFieldError(input, errorEl) {
    input.classList.remove('error');
    errorEl.classList.remove('show');
  }
  // login.js / my_profile.js: 위 함수들 직접 사용 (스크립트 순서 보장)
  ```

### R4. 비밀번호 검증 정책 중앙화 [중 · 중]
- **왜 필요?**: 클라(login.js + my_profile.js) + 백엔드 3곳에 동일 정책. 정책 변경 시 한 곳 누락 위험. login은 8+, my_profile은 8~16 → 이미 어긋남.
- **장점**: 진실 원천 단일화 / 백엔드 변경 자동 반영.
- **단점**: 백엔드가 정책 노출 endpoint 필요 또는 app_config 주입.
- **변경 위치**:
  - 옵션 A: 백엔드 GET `/api/auth/policy/` → JS는 시작 시 fetch + 캐시
  - 옵션 B: components/app_config.html에 정책 상수 주입
- **변경 예시 (B)**:
  ```html
  <!-- app_config.html -->
  <script>
    window.AppConfig.passwordPolicy = {
      minLength: 8, maxLength: 16,
      requiredKinds: 2, // 영문/숫자/특수 중 2종
    };
  </script>
  ```
  ```js
  // shared/validators.js
  function validatePassword(val, policy = window.AppConfig.passwordPolicy) {
    if (!val) return MSG.required;
    if (val.length < policy.minLength || val.length > policy.maxLength) return MSG.length;
    const kinds = [/[a-zA-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter(r => r.test(val)).length;
    if (kinds < policy.requiredKinds) return MSG.pattern;
    return '';
  }
  ```

### R5. AppConfig fallback 일관화 [하 · 소]
- **왜 필요?**: login.js submit과 Auth._resolveUrl이 같은 fallback 로직을 다르게 표현.
- **장점**: 한 곳에서 관리.
- **단점**: 없음.
- **변경 위치**: [login.js:126-127](../../../drf-server/static/js/auth/login.js#L126), [auth.js:42-46](../../../drf-server/static/js/shared/auth.js#L42).
- **변경 예시**:
  ```js
  // login.js submit 내부
  // before
  const url = (window.AppConfig && window.AppConfig.apiUrl)
    ? window.AppConfig.apiUrl('/api/auth/login/') : '/api/auth/login/';

  // after — Auth._resolveUrl을 외부 노출 또는 별도 헬퍼
  const url = AppConfig.apiUrl('/api/auth/login/');
  ```

### R6. logout API 실패 시 사용자 피드백 [중 · 소]
- **왜 필요?**: 현재 try-finally로 API 실패해도 success 모달 노출 → LoginLog 기록 누락 silent.
- **장점**: 운영 가시성 / 감사 트레일.
- **단점**: 사용자에게 "로그아웃 실패" 노출은 UX 혼란 — 토큰은 클라이언트 측에서 제거되었는데도 실패로 보임.
- **변경 위치**: [layout.js:182-189](../../../drf-server/static/js/shared/layout.js#L182-L189)
- **변경 예시**:
  ```js
  logoutConfirm?.addEventListener('click', async () => {
    let apiOk = true;
    try { const res = await Auth.apiFetch('/api/auth/logout/', { method: 'POST' });
          apiOk = res.ok; }
    catch { apiOk = false; }
    finally {
      modal.style.display = 'none';
      successModal.style.display = 'flex';
      if (!apiOk) console.warn('logout API failed but session cleared locally');
    }
  });
  ```

### R7. catch {} 광범위 → console.warn [하 · 소]
- **왜 필요?**: `Auth.getMe` 등의 silent catch는 디버깅 어려움.
- **장점**: 운영 가시성.
- **변경 위치**: [auth.js:97-99](../../../drf-server/static/js/shared/auth.js#L97-L99) 등.
- **변경 예시**:
  ```js
  } catch (e) {
    console.warn('[Auth.getMe]', e);
    return null;
  }
  ```

### R8. PasswordModal submit 응답 형식 defensive [하 · 소]
- **왜 필요?**: `data.current_password[0]` 형식 가정. 백엔드 응답이 다른 형식(string, dict)으로 변경되면 NPE.
- **장점**: 백엔드 변경 회복 탄력성.
- **변경 위치**: [my_profile.js:212-216](../../../drf-server/static/js/detail/my_profile.js#L212-L216)
- **변경 예시**:
  ```js
  function pickError(field, fallback) {
    const v = data[field];
    if (Array.isArray(v) && v.length) return v[0];
    if (typeof v === 'string') return v;
    return fallback;
  }
  if (data.current_password) this._showError('current', pickError('current_password', PWD_MSG.current.wrong));
  ```

### R9. modal backdrop 닫기 일관 [하 · 소]
- **왜 필요?**: logout success modal과 password success modal이 backdrop 닫기 미지원 → UX 일관성 부족.
- **변경 위치**: [layout.js, my_profile.js].
- **변경 예시**: 공통 `shared/modal.js::bindBackdropClose(modal, onClose)` 헬퍼 도입.

### R10. Auth 메서드 키 상수화 [하 · 소]
- **왜 필요?**: setTokens·clear·_refresh 모두 `'access_token'/'refresh_token'/'username'/'role'` 4개 키 직접 사용. 추가 시 한쪽 누락 가능.
- **변경 위치**: [auth.js](../../../drf-server/static/js/shared/auth.js) 상단.
- **변경 예시**:
  ```js
  const KEYS = {
    access: 'access_token',
    refresh: 'refresh_token',
    username: 'username',
    role: 'role',
  };
  // setItem(KEYS.access, ...), removeItem(KEYS.access) 등
  ```

## 6. 단계별 적용 순서

### 1단계 — 즉시 (1일) ⚡
- **R1** _refresh 동시성 가드 — 가장 큰 효과·작은 변경. 단독 PR.
- **R7** catch {} → console.warn — grep으로 일괄 변경.
- **이유**: 코드 변경 작은데 회귀 위험 거의 없음. 실제 사고 잠재력 큼.

### 2단계 — 1주 내 🔧
- **R2** apiFetch redirectLogin 흐름 명확화 (호출자 코드 정리 동반)
- **R6** logout API 실패 시 console.warn (감사 트레일 보강)
- **R8** PasswordModal 응답 defensive
- **이유**: 호출자 코드 갱신이 동반되지만 작음. R2는 R1 적용 후 진행 권장.

### 3단계 — 다음 sprint 🏗
- **R3** 폼 에러 헬퍼 추출 (form-errors.js)
- **R4** 비밀번호 검증 정책 중앙화
- **R5** AppConfig fallback 일관화
- **R9** modal backdrop 일관 (shared/modal.js 베이스)
- **R10** Auth 키 상수화
- **이유**: 신규 모듈·정책 결정 동반. 현재 동작에 영향 없으나 PR 리뷰 시간 필요.

### ⚠️ 주의사항 (초보자용)

- **R1 적용 시 backward compat 확인**: 다른 코드가 `Auth._refresh`를 직접 호출하지 않는지 grep — 현재는 apiFetch만 호출. 안전.
- **R2 적용 시 호출자 추적 필수**: `Auth.apiFetch` 호출자 40+ 곳 중 res.status === 401 한 번 더 체크하는 곳을 모두 찾아 정리. 한 번에 변경하면 회귀 가능. PR 두 개로 — ① apiFetch에 throw 추가 + 옵션화 → ② 호출자 정리.
- **R4 정책 중앙화는 백엔드 협업 필요**: app_config 주입은 server-side render 시점이라 Django context 변경. 옵션 A(API)는 fetch 시점 의존성. 옵션 결정 후 진행.
- **R6 로그 추가 시 운영 alert 정책 합의**: console.warn은 클라이언트 콘솔에만 — 운영팀이 못 봄. Sentry 등 운영 로깅 도구 도입 시 의미 있음.
- **모든 변경 후 e2e 회귀 검증**: 로그인/로그아웃/비밀번호 변경/세션 만료 4종 시나리오 수동 또는 PR-H 통합 테스트 확장.
