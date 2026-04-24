# LG-03 로그인 실행 — 코드 검토 보고서

> 작성자: 한지혜 / 작성일: 2026-04-24
> 대상 기능 ID: **LG-03** (로그인 실행)
> 검토 범위: 프론트엔드(실행 흐름) + 백엔드(인증 API, 토큰 발급)

---

## 1. 기능 정의서 스펙 요약

| 항목 | 내용 |
|------|------|
| 기능 목적 | 인증 성공 시 메인 진입 |
| 사용자 시나리오 | 로그인 버튼 클릭 또는 Enter, 유효성 검사, 성공 시 메인 이동 |
| 수집 정보 | 아이디, 비밀번호 |
| 디자인 요소 | 로그인 버튼, 로딩 상태 |
| 유효성 처리 | auth 전 필수값 및 형식 검사 |
| 예외 조건 | **중복 클릭 방지** |
| 에러 처리 | 인증 실패 시 실패 메시지 반환 |
| 백엔드 처리 | 인증 API, **세션 발급**, 사용자 권한 반환 |
| 프론트엔드 처리 | 버튼 비활성/로딩, 성공 시 라우팅 |
| 참고사항 | **세션 만료 정책 별도 정의 필요** |

---

## 2. 검토 대상 파일

| 역할 | 파일 경로 |
|------|-----------|
| 로그인 실행 JS | `drf-server/templates/auth/login.html` 188~230줄 |
| 인증 API View | `drf-server/apps/accounts/views.py` |
| 유효성 Serializer | `drf-server/apps/accounts/serializers.py` |
| JWT 설정 | `drf-server/config/settings.py` 139~144줄 |
| 토큰 관리 모듈 | `drf-server/static/js/refactors/auth.js` |

---

## 3. 스펙 충족 항목 ✅

### 프론트엔드 — 실행 흐름

| 항목 | 구현 위치 | 확인 내용 |
|------|-----------|-----------|
| 버튼 클릭으로 실행 | `login.html` 188줄 | `form.addEventListener('submit', ...)` |
| Enter 키로 실행 | `login.html` 188줄 | form submit 이벤트 — 필드 어디서든 Enter 동작 |
| auth 전 유효성 검사 | `login.html` 195~199줄 | `validateUsername()` + `validatePassword()` 통과 후에만 API 호출 |
| 버튼 비활성화 (중복 클릭 방지) | `login.html` 201줄 | `btn.disabled = true` |
| Enter 키 중복 제출 방지 | `login.html` 201줄 | HTML 스펙상 폼의 유일한 submit 버튼이 disabled이면 Enter 키도 자동 차단 |
| 로딩 텍스트 표시 | `login.html` 202줄 | `btn.textContent = '로그인 중...'` |
| CSS disabled 스타일 | `login.css` 92줄 | `background:#90a4c8; cursor:not-allowed` |
| 인증 실패 에러 표시 | `login.html` 212~214줄 | `showServerError(data.error \|\| MSG.server.authFail)` |
| 네트워크 오류 처리 | `login.html` 223~225줄 | `catch { showServerError(MSG.server.networkFail) }` |
| 성공 시 대시보드 이동 | `login.html` 222줄 | `window.location.href = '/dashboard/'` |
| 버튼 상태 복구 | `login.html` 225~228줄 | `finally { btn.disabled=false; btn.textContent='로그인' }` |
| 아이디 공백 제거 | `login.html` 192줄 | `usernameInput.value.trim()` |
| 비밀번호 trim 미적용 | `login.html` 193줄 | `passwordInput.value` — 비밀번호는 공백 포함 허용, 올바른 처리 |

### 백엔드 — 인증 API

| 항목 | 구현 위치 | 확인 내용 |
|------|-----------|-----------|
| POST /api/auth/login/ | `views.py` 23줄 | `LoginView.post()` |
| 비로그인 접근 허용 | `views.py` 24줄 | `permission_classes = [AllowAny]` |
| 인증 처리 | `serializers.py` 59~63줄 | `authenticate()` 호출 |
| Access Token 발급 | `views.py` 79~80줄 | `RefreshToken.for_user(user).access_token` |
| Refresh Token 발급 | `views.py` 82줄 | `str(refresh)` |
| 사용자 권한 반환 | `views.py` 85줄 | `"role": user.user_type` |
| 응답 구조 4항목 | `views.py` 80~87줄 | `access`, `refresh`, `username`, `role` |

### 프론트-백엔드 데이터 일치 확인

| 키 | 백엔드 반환 | 프론트 저장 | auth.js 읽기 | 일치 |
|----|------------|------------|-------------|------|
| `access_token` | `access` | `login.html` 217줄 | `getAccessToken()` | ✅ |
| `refresh_token` | `refresh` | `login.html` 218줄 | `clear()` | ✅ |
| `username` | `username` | `login.html` 219줄 | `getUsername()` | ✅ |
| `role` | `role` | `login.html` 220줄 | `getRole()` | ✅ |

### JWT 만료 설정

| 항목 | 설정값 | 위치 |
|------|--------|------|
| Access Token 유효기간 | **24시간** | `settings.py` 141줄 |
| Refresh Token 유효기간 | **30일** | `settings.py` 142줄 |
| 인증 헤더 방식 | Bearer | `settings.py` 143줄 |

---

## 4. 이슈 항목

### 🟡 MEDIUM — 인지 및 협의 필요

---

#### M-1. 스펙 "세션 발급" 표현과 JWT 구현 불일치

**스펙 백엔드 처리:** "인증 API, **세션 발급**, 사용자 권한 반환"
**실제 구현:** Django 세션(Session)이 아닌 **JWT (stateless 토큰)**

```python
# settings.py — JWT 인증 사용 중
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
}
```

Django의 `SessionMiddleware`는 MIDDLEWARE에 등록되어 있지만, 로그인 인증 자체는 JWT 기반으로 동작합니다. 토큰은 서버가 아닌 클라이언트(localStorage)에 저장됩니다.

코드 버그가 아닌 **스펙 용어 문제**입니다. 팀 내에서 "세션"을 JWT 토큰 세션과 동의어로 사용하는지, 추후 Django 세션으로 전환할 계획인지 확인이 필요합니다.

---

#### M-2. 세션 만료 정책 미문서화

**스펙 요구사항:**
> "참고사항: 세션 만료 정책 별도 정의 필요"

현재 JWT 만료 설정이 `settings.py` 코드 안에만 존재하고, 팀이 참고할 공식 정책 문서가 없습니다.

**정책 문서화가 필요한 내용:**

| 항목 | 현재 설정 | 결정 필요 사항 |
|------|-----------|----------------|
| Access Token 유효기간 | 24시간 | 보안 정책상 적절한 시간인지 팀 합의 필요 |
| Refresh Token 유효기간 | 30일 | 장기 미접속 후 재로그인 주기 합의 필요 |
| 만료 후 처리 | 로그인 화면 이동 | 자동 갱신(silent refresh) 여부 결정 필요 |
| 잠금 계정 토큰 처리 | 미정 | 계정 잠금 시 기존 발급 토큰 즉시 무효화 여부 |

> 스펙에서 명시적으로 "별도 정의 필요"라고 했으나, 현재 아무 문서도 없는 상태입니다.

---

### 🟢 LOW — 장기 개선 고려

---

#### L-1. Refresh Token 자동 갱신 미구현

**위치:** `static/js/refactors/auth.js`

```javascript
async getMe() {
    const res = await this.apiFetch('/api/auth/me/');
    if (res.status === 401) { this.redirectLogin(); return null; }
    // 401 시 refresh token으로 재시도하는 로직 없음
},
```

`/api/auth/token/refresh/` 엔드포인트가 `urls.py`에 등록되어 있지만, 클라이언트 `auth.js`에서 활용하지 않습니다. Access Token 24시간이 만료되면 자동 갱신 없이 바로 로그인 화면으로 이동합니다.

현재 24시간이라 당장 큰 문제는 아니지만, M-2의 세션 만료 정책이 확정되면 함께 구현이 필요합니다.

---

#### L-2. 성공 후 라우팅 URL 하드코딩

**위치:** `templates/auth/login.html` 222줄

```javascript
window.location.href = '/dashboard/';
```

현재 스펙에서는 단순 메인 이동이므로 허용 범위입니다. 추후 역할(role)별로 진입 화면이 다르게 요구되면 재검토가 필요합니다.

---

## 5. 하드코딩 점검

| 항목 | 위치 | 판단 |
|------|------|------|
| API URL `/api/auth/login/` | `login.html` 205줄 | ✅ 허용 범위 |
| 리다이렉트 URL `/dashboard/` | `login.html` 222줄 | 🟢 역할 기반 라우팅 필요 시 재검토 |
| Access Token 24시간 | `settings.py` 141줄 | ✅ 보안 정책값 — 환경별로 다를 필요 없음 |
| Refresh Token 30일 | `settings.py` 142줄 | ✅ 동일 |
| localStorage 키 이름 | `login.html` + `auth.js` | ✅ 양쪽 완전 일치 |

> JWT 만료 시간은 SECRET_KEY나 ALLOWED_HOSTS처럼 환경마다 달라야 하는 값이 아닌 **보안 정책값**입니다. 현재 규모에서 코드에 직접 유지하는 것이 더 명확합니다.

---

## 6. 기능 로직 검증

### 프론트엔드 submit 흐름

```
[버튼 클릭 OR Enter]
        ↓
  e.preventDefault()
  clearServerError()
        ↓
  validateUsername() + validatePassword()
  → 실패: showFieldError() + return (API 호출 없음)
        ↓ (유효성 통과)
  btn.disabled = true  ←  Enter 키 재입력도 동시 차단 (HTML 스펙)
  btn.textContent = '로그인 중...'
        ↓
  POST /api/auth/login/ { username, password }
        ↓
  !res.ok → showServerError(data.error || MSG.server.authFail) + return
        ↓ (200 OK)
  localStorage 4항목 저장
  window.location.href = '/dashboard/'
        ↓ (네트워크 오류)
  catch → showServerError(MSG.server.networkFail)
        ↓ (성공·실패·오류 모든 경로)
  finally → btn.disabled=false + '로그인' 복구
```

→ 성공 / 인증 실패 / 네트워크 오류 3개 경로 모두 처리 ✅

### 백엔드 인증 흐름

```
POST /api/auth/login/
        ↓
  LoginSerializer.validate()
    잠금 확인 → 비활성 확인 → authenticate()
    → 실패: record_failed_login() + LoginLog(FAILED_*)
    → 성공: reset_failed_login()
        ↓
  LoginLog(SUCCESS) 기록
        ↓
  RefreshToken.for_user(user)
        ↓
  Response { access, refresh, username, role }
```

→ 백엔드 인증 흐름 정상 ✅

### 중복 제출 방지 검증

```
btn.disabled = true 상태에서:
  - 버튼 클릭     → disabled 버튼 클릭 불가 ✅
  - Enter 키 입력 → HTML 스펙: 폼의 유일한 submit 버튼이 disabled이면
                    브라우저가 submit 이벤트 자체를 발생시키지 않음 ✅
```

> 별도의 `if (btn.disabled) return;` guard 코드 없이도 완전한 중복 제출 방지가 보장됩니다.

---

## 7. 종합 요약

| 구분 | 항목 수 | 항목 |
|------|---------|------|
| ✅ 충족 | 15개 | 버튼·Enter 실행, 유효성 선검사, 중복제출방지(클릭+Enter), 로딩상태, 버튼복구, 에러표시, 네트워크오류, 성공라우팅, JWT발급, 권한반환, trim처리, localStorage 4항목 저장·일치, CSRF 불필요 |
| 🟡 MEDIUM | 2개 | M-1 세션/JWT 용어 불일치 (스펙 문서), M-2 세션 만료 정책 미문서화 |
| 🟢 LOW | 2개 | L-1 Refresh Token 자동 갱신 미구현, L-2 라우팅 URL 하드코딩 |
| 수정 없음 | — | 코드 품질 양호. M-1·M-2는 팀 협의 및 문서 작업 사항 |

---

## 8. Action Items

| 순서 | 항목 | 담당 | 비고 |
|------|------|------|------|
| 1 | M-2 세션 만료 정책 문서 작성 | PM/백엔드 | access 24h / refresh 30d / 갱신 여부 / 잠금 처리 4가지 확정 |
| 2 | M-1 스펙 "세션 발급" 표현 수정 | PM | JWT 발급으로 표현 통일 |
| 3 | L-1 Refresh Token 자동 갱신 | 프론트 | M-2 정책 확정 후 구현 |

---

## 9. 잘 구현된 부분 (유지)

- **3개 경로 완전 처리**: 성공 / 인증 실패 / 네트워크 오류 모두 처리되어 어떤 경우에도 UI가 막히지 않음
- **finally 버튼 복구**: 어떤 경로로 종료되어도 버튼이 반드시 원상복구됨
- **중복 제출 완전 방지**: `btn.disabled = true` 하나로 클릭·Enter 모두 차단 — HTML 스펙 기반 동작
- **비밀번호 trim 미적용**: 공백 포함 비밀번호를 올바르게 처리
- **프론트↔백엔드 키 완전 일치**: `login.html` 저장 키와 `auth.js` 읽기 키가 4개 모두 동일
- **CSRF 불필요**: JWT 기반 `APIView`는 DRF에서 `csrf_exempt` 처리됨 — 별도 토큰 없이 정상 동작
- **에러 메시지 MSG 객체**: 서버 fallback 메시지도 `MSG.server.*`로 분리되어 관리 용이
