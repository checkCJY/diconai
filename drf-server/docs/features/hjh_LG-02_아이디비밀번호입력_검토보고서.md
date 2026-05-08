# LG-02 아이디/비밀번호 입력 — 코드 검토 보고서

> 작성자: 한지혜 / 작성일: 2026-04-23
> 대상 기능 ID: **LG-02** (아이디/비밀번호 입력)
> 검토 범위: 프론트엔드 + 백엔드 유효성 검사

---

## 1. 기능 정의서 스펙 요약

| 항목 | 내용 |
|------|------|
| 기능 목적 | 인증 정보 입력 수집 |
| 사용자 시나리오 | 필드 focus, 값 입력, clear 버튼 활성, 비밀번호 마스킹 |
| 수집 정보 | 아이디, 비밀번호 |
| 디자인 요소 | 입력필드 2개, clear 아이콘, 마스킹 텍스트 |
| 유효성 처리 | 아이디 4~20자 영문/숫자, 비밀번호 8자 이상 2종 조합 |
| 예외 조건 | Enter 입력 지원, clear 클릭 시 전체 삭제 |
| 에러 처리 | 필드 단위 오류문구 노출 |
| 백엔드 처리 | Submit 전 클라이언트 유효성 검사 |
| 프론트엔드 처리 | **focus/blur**, clear, mask, **error 상태관리** |
| 참고사항 | **에러문구는 메시지정의 시트 분리** |

---

## 2. 검토 대상 파일

| 역할 | 파일 경로 |
|------|-----------|
| 화면 + 유효성 JS | `drf-server/templates/auth/login.html` |
| 스타일 | `drf-server/static/css/auth/login.css` |
| 서버 유효성 검사 | `drf-server/apps/accounts/serializers.py` |

---

## 3. 스펙 충족 항목 ✅

### 입력 필드 구성

| 항목 | 구현 위치 | 확인 내용 |
|------|-----------|-----------|
| 아이디 입력 필드 | `login.html` 36~38줄 | `type="text"`, `id="username"`, `maxlength="20"`, `autocomplete="username"` |
| 비밀번호 입력 필드 | `login.html` 47~49줄 | `type="password"`, `id="password"`, `maxlength="100"`, `autocomplete="current-password"` |
| label 연결 | `login.html` 34줄, 45줄 | `<label for="username">`, `<label for="password">` — 접근성 기준 충족 |
| 비밀번호 마스킹 | `login.html` 47줄 | `type="password"` — 브라우저 기본 마스킹 |

### clear 버튼 동작

| 항목 | 구현 위치 | 확인 내용 |
|------|-----------|-----------|
| clear 버튼 존재 | `login.html` 38줄, 49줄 | 아이디/비밀번호 각각 `✕` 버튼 |
| 입력 시 버튼 활성화 | `login.html` 89~96줄 `syncClear()` | `input` 이벤트에서 `visible` 클래스 토글 |
| clear 클릭 시 값 삭제 | `login.html` 97~108줄 | `value = ''` + `classList.remove('visible')` |
| clear 후 포커스 복귀 | `login.html` 100줄, 106줄 | `input.focus()` 호출 |
| clear 후 에러 초기화 | `login.html` 101줄, 107줄 | `clearFieldError()` 호출 |

### 유효성 검사 — 프론트엔드

| 규칙 | 구현 위치 | 에러 메시지 |
|------|-----------|-------------|
| 아이디 미입력 | `login.html` 132줄 | "아이디를 입력해주세요." |
| 아이디 형식 (영문/숫자) | `login.html` 133줄 | "아이디는 영문 또는 숫자만 입력할 수 있습니다." |
| 아이디 길이 (4~20자) | `login.html` 134줄 | "아이디를 4~20자로 입력해주세요." |
| 비밀번호 미입력 | `login.html` 138줄 | "비밀번호를 입력해주세요." |
| 비밀번호 최소 길이 (8자) | `login.html` 139줄 | "비밀번호를 8자 이상 입력해야 합니다." |
| 비밀번호 2종 조합 | `login.html` 140~141줄 | "비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다." |

### 유효성 검사 — 백엔드 (이중 검증)

| 규칙 | 구현 위치 |
|------|-----------|
| 아이디 형식 | `serializers.py` 18~23줄 `validate_username()` |
| 비밀번호 규칙 | `serializers.py` 26~33줄 `validate_password()` |
| 프론트↔백엔드 메시지 일치 여부 | ✅ 모든 에러 메시지 문자열 동일 |

### 기타 동작

| 항목 | 확인 |
|------|------|
| Enter 키 지원 | ✅ `form.addEventListener('submit')` 방식 — 폼 내 어디서든 Enter 시 submit 발생 |
| Submit 전 유효성 검사 | ✅ `e.preventDefault()` 후 검사 → 통과 시에만 API 호출 |
| 두 필드 동시 에러 표시 | ✅ 두 필드 모두 검사 후 각각 에러 표시 (한 필드만 막지 않음) |
| 입력 시 에러 자동 해제 | ✅ `input` 이벤트에서 `clearFieldError()` 호출 |
| CSS focus 스타일 | ✅ `login.css` 55줄 — 파란 테두리 + 글로우 |
| CSS error 스타일 | ✅ `login.css` 74줄 — 빨간 테두리 + 글로우 |

---

## 4. 문제 항목 — 심각도별 분류

### 🟡 MEDIUM — 운영 전 수정 권장

---

#### M-1. blur 이벤트 미구현

**위치:** `templates/auth/login.html` JS 전체

**스펙 요구사항:**
> "프론트엔드 처리: **focus/blur**, clear, mask, error 상태관리"

**현재 코드에 blur 이벤트 리스너가 없음:**
```javascript
// input 이벤트만 있음 — blur 이벤트 없음
usernameInput.addEventListener('input', () => { ... });
passwordInput.addEventListener('input', () => { ... });
```

**문제점:**
- 사용자가 아이디 입력 후 탭/클릭으로 다음 필드로 이동해도 에러가 즉시 표시되지 않음
- 에러 피드백이 submit 버튼 클릭 시점까지 지연됨
- 스펙이 blur 상태관리를 명시하고 있음

**권장 수정 방향:**
```javascript
// blur 시 유효성 검사 실행
usernameInput.addEventListener('blur', () => {
    const err = validateUsername(usernameInput.value.trim());
    if (err) showFieldError(usernameInput, usernameError, err);
});
passwordInput.addEventListener('blur', () => {
    const err = validatePassword(passwordInput.value);
    if (err) showFieldError(passwordInput, passwordError, err);
});
```

---

#### M-2. 에러 메시지 메시지 시트 미분리

**위치:** `templates/auth/login.html` 132~141줄 / `apps/accounts/serializers.py` 19~32줄

**스펙 요구사항:**
> "참고사항: 에러문구는 메시지정의 시트 분리"

**현재: JS 함수 안과 serializers.py 안에 각각 하드코딩**

```javascript
// login.html — 한국어 문자열 직접 리터럴
function validateUsername(val) {
    if (!val) return '아이디를 입력해주세요.';
    if (!/^[a-zA-Z0-9]+$/.test(val)) return '아이디는 영문 또는 숫자만 입력할 수 있습니다.';
    if (val.length < 4 || val.length > 20) return '아이디를 4~20자로 입력해주세요.';
    return '';
}
```
```python
# serializers.py — 동일 문자열 별도 하드코딩
raise serializers.ValidationError("아이디는 영문 또는 숫자만 입력할 수 있습니다.")
raise serializers.ValidationError("아이디를 4~20자로 입력해주세요.")
```

**현재 두 파일의 메시지 일치 여부 확인:**

| 에러 상황 | login.html | serializers.py | 일치 |
|-----------|-----------|----------------|------|
| 아이디 형식 오류 | "아이디는 영문 또는 숫자만 입력할 수 있습니다." | 동일 | ✅ |
| 아이디 길이 오류 | "아이디를 4~20자로 입력해주세요." | 동일 | ✅ |
| 비밀번호 길이 오류 | "비밀번호를 8자 이상 입력해야 합니다." | 동일 | ✅ |
| 비밀번호 조합 오류 | "비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다." | 동일 | ✅ |

현재는 일치하지만, 어느 한 쪽만 수정하면 불일치 발생 위험이 있음.

**권장 수정 방향 — JS 메시지 객체 분리:**
```javascript
// 상단에 메시지 객체 정의
const MSG = {
    username: {
        required: '아이디를 입력해주세요.',
        format:   '아이디는 영문 또는 숫자만 입력할 수 있습니다.',
        length:   '아이디를 4~20자로 입력해주세요.',
    },
    password: {
        required: '비밀번호를 입력해주세요.',
        length:   '비밀번호를 8자 이상 입력해야 합니다.',
        pattern:  '비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다.',
    },
};
// 함수에서 참조
function validateUsername(val) {
    if (!val) return MSG.username.required;
    if (!/^[a-zA-Z0-9]+$/.test(val)) return MSG.username.format;
    if (val.length < 4 || val.length > 20) return MSG.username.length;
    return '';
}
```

> 백엔드 메시지 분리는 Django `ValidationError`에 코드 인자를 사용하거나 별도 `messages.py` 파일로 관리 가능. 현재 프로젝트 규모에서는 JS 쪽만 분리해도 충분.

---

### 🟢 LOW — 장기 개선 고려

---

#### L-1. 서버 측 비밀번호 최대 길이 미검증

**위치:** `apps/accounts/serializers.py` 26~33줄

```python
def validate_password(self, value):
    if len(value) < 8:   # 최솟값만 있음
        raise serializers.ValidationError("비밀번호를 8자 이상 입력해야 합니다.")
    # 최대 길이 검증 없음
```

HTML에 `maxlength="100"`이 있지만 API를 직접 호출하면 100자 초과 입력이 가능.
bcrypt 등 해시 함수는 입력이 매우 길 경우 성능 저하가 생길 수 있으므로 서버에서도 `len(value) <= 100` 검증 권장.

---

#### L-2. 웹 접근성(Accessibility) 미적용

현재 에러 상태를 시각적으로만 표현하고 스크린리더 지원이 없음.

```html
<!-- 현재 -->
<div class="field-error" id="usernameError"></div>

<!-- 권장 -->
<div class="field-error" id="usernameError" role="alert" aria-live="polite"></div>
```

`role="alert"`를 추가하면 에러 메시지가 표시될 때 스크린리더가 자동 읽어줌.
스펙에 명시는 없으나 공공 서비스 특성상 웹 접근성 고려 권장.

---

#### L-3. 아이디 유효성 검사 순서 (미세 UX)

**위치:** `templates/auth/login.html` 131~135줄

현재 순서: **빈값 → 형식(영문/숫자) → 길이(4~20자)**

```javascript
if (!val)                               return '아이디를 입력해주세요.';
if (!/^[a-zA-Z0-9]+$/.test(val))       return '영문 또는 숫자만...';   // 형식 먼저
if (val.length < 4 || val.length > 20) return '4~20자로...';           // 길이 나중
```

예: `"ab!"` 입력 → 형식 에러 먼저 나옴 (적절)
예: `"abc"` 입력 (3자, 유효 문자) → 형식은 통과, 길이 에러 (적절)

현재 순서도 나쁘지 않음. 다만 일부 서비스는 길이를 형식보다 먼저 검사하는 경우도 있어 팀 컨벤션으로 결정 권장.

---

## 5. 하드코딩 점검

| 항목 | 위치 | 판단 |
|------|------|------|
| 에러 메시지 문자열 | `login.html` validateUsername/validatePassword | 🟡 메시지 객체 분리 권장 |
| 에러 메시지 문자열 | `serializers.py` validate_username/validate_password | 🟡 메시지 객체 분리 권장 |
| 아이디 최소 길이 `4` | `login.html` 134줄, `serializers.py` 23줄 | ✅ 비즈니스 규칙값 — 하드코딩 허용 |
| 아이디 최대 길이 `20` | `login.html` 134줄, `serializers.py` 23줄 + HTML maxlength | ✅ 동일 |
| 비밀번호 최소 길이 `8` | `login.html` 139줄, `serializers.py` 27줄 | ✅ 비즈니스 규칙값 — 하드코딩 허용 |
| 비밀번호 최대 길이 `100` | `login.html` maxlength 속성 | 🟢 serializers.py에도 추가 권장 |
| 정규식 패턴 | `login.html` 133줄, `serializers.py` 18줄 | ✅ 비즈니스 규칙 — 하드코딩 허용 |
| API URL `/api/auth/login/` | `login.html` 174줄 | 🟢 상수화 고려 가능, 현 규모에서 허용 |

---

## 6. 기능 로직 검증

### 유효성 검사 흐름

```
[submit 클릭 또는 Enter]
        ↓
  e.preventDefault()
        ↓
  validateUsername() → 에러 있으면 showFieldError() (아이디)
  validatePassword() → 에러 있으면 showFieldError() (비밀번호)
        ↓
  둘 중 하나라도 에러 → return (API 호출 차단)
        ↓
  btn.disabled = true + '로그인 중...'
        ↓
  POST /api/auth/login/
        ↓
  (서버에서도 동일 규칙으로 재검증)
```

→ 프론트-백엔드 이중 검증 구조 ✅

### clear 버튼 흐름

```
[입력 발생]
  syncClear() → 값 있으면 clear 버튼 visible

[clear 클릭]
  value = '' → visible 제거 → focus() → clearFieldError()
```

→ 에러 상태, 버튼 상태, 포커스 모두 일관성 있게 처리 ✅

### 에러 표시/해제 흐름

```
[submit 시] showFieldError() → input.classList.add('error') + errorEl.show
[입력 시]   clearFieldError() → input.classList.remove('error') + errorEl.hide
```

→ 에러 발생과 해제 타이밍 자연스러움 ✅
→ 단, blur 시 에러 표시 없음 (M-1 참고)

---

## 7. 종합 요약

| 구분 | 항목 수 | 항목 |
|------|---------|------|
| ✅ 충족 | 18개 | 입력필드 구성, clear 버튼 5동작, 유효성 6규칙, Enter 지원, 이중검증, 동시에러표시, 에러자동해제, focus 스타일, error 스타일 |
| 🟡 MEDIUM | 2개 | M-1 blur 미구현, M-2 에러 메시지 미분리 |
| 🟢 LOW | 3개 | L-1 서버 maxlength, L-2 웹 접근성, L-3 검사 순서 |

---

## 8. 수정 우선순위 Action Items

| 순서 | 항목 | 담당 | 예상 공수 |
|------|------|------|-----------|
| 1 | M-1 blur 이벤트 추가 | 프론트 | 30min |
| 2 | M-2 JS 에러 메시지 객체 분리 | 프론트 | 30min |
| 3 | L-1 serializers.py 비밀번호 최대 길이 추가 | 백엔드 | 10min |
| 4 | L-2 field-error에 role="alert" 추가 | 프론트 | 10min |

---

---

## 10. 수정 이력 (2026-04-23)

> 검토 보고서 작성 후 4가지 항목 수정 완료.

---

### M-1 수정 — blur 이벤트 추가

**수정 파일:** `templates/auth/login.html`

```javascript
/* ── blur: 값이 있을 때만 유효성 검사 (빈 값은 submit 시점에 처리) ── */
usernameInput.addEventListener('blur', () => {
    if (!usernameInput.value) return;
    const err = validateUsername(usernameInput.value.trim());
    if (err) showFieldError(usernameInput, usernameError, err);
});
passwordInput.addEventListener('blur', () => {
    if (!passwordInput.value) return;
    const err = validatePassword(passwordInput.value);
    if (err) showFieldError(passwordInput, passwordError, err);
});
```

**검증:**
- 빈 값 blur 시 조기 return → "아이디를 입력해주세요." 에러가 blur 시점에 나오지 않음 ✅
- 값이 있고 형식이 틀렸을 때만 blur에서 에러 표시 ✅
- input 이벤트에서 `clearFieldError()` 호출 → 사용자가 수정 시작하면 에러 바로 사라짐 ✅
- clear 버튼 클릭 시: blur → validation(brief) → click → clearFieldError 순서로 동작. 최종 상태는 에러 없음으로 정리됨 ✅

**이벤트 흐름:**
```
[값 있는 상태에서 blur]  → 유효성 검사 → 에러 있으면 표시
[입력 시작 (input)]      → clearFieldError → 에러 즉시 해제
[submit]                 → 빈 값 포함 전체 검사
```

---

### M-2 수정 — 에러 메시지 MSG 객체 분리

**수정 파일:** `templates/auth/login.html`

JS IIFE 상단에 `MSG` 상수 객체 추가. 유효성 검사 함수와 서버 에러 핸들러 모두 문자열 리터럴 대신 `MSG.*` 참조로 변경.

```javascript
const MSG = {
    username: {
        required: '아이디를 입력해주세요.',
        format:   '아이디는 영문 또는 숫자만 입력할 수 있습니다.',
        length:   '아이디를 4~20자로 입력해주세요.',
    },
    password: {
        required:  '비밀번호를 입력해주세요.',
        minLength: '비밀번호를 8자 이상 입력해야 합니다.',
        pattern:   '비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다.',
    },
    server: {
        authFail:    '아이디 또는 비밀번호가 올바르지 않습니다.',
        networkFail: '서버에 연결할 수 없습니다.',
    },
};
```

**포함 범위:** 필드 유효성 메시지(6개) + 서버 응답 fallback 메시지(1개) + 네트워크 오류 메시지(1개) 총 8개 문자열 분리.

**검증:**
- `validateUsername()` → `MSG.username.*` 참조 ✅
- `validatePassword()` → `MSG.password.*` 참조 ✅
- `showServerError(data.error || MSG.server.authFail)` → 서버가 내려준 에러 우선, fallback만 MSG 참조 ✅
- `showServerError(MSG.server.networkFail)` ✅

---

### L-1 수정 — 비밀번호 최대 길이 서버 검증

**수정 파일:** `apps/accounts/serializers.py`

`validate_password()` 코드 추가 대신 **DRF `CharField` 필드 수준 `max_length`** 방식으로 처리.

```python
# 변경 전
password = serializers.CharField(write_only=True)

# 변경 후
password = serializers.CharField(
    write_only=True,
    max_length=100,
    error_messages={"max_length": "비밀번호는 100자 이하로 입력해주세요."},
)
```

**검증:**
- 필드 수준 검증은 `validate_password()` 실행 전에 처리됨 → API 직접 호출로 100자 초과 입력 차단 ✅
- `error_messages` 오버라이드로 한국어 메시지 반환 ✅
- `validate_password()` 코드 수정 없음 — 기존 최솟값 검증과 충돌 없음 ✅

---

### L-2 수정 — 웹 접근성 속성 추가

**수정 파일:** `templates/auth/login.html`

| 요소 | 추가 속성 | 효과 |
|------|-----------|------|
| `<input id="username">` | `aria-describedby="usernameError"` | 포커스 시 스크린리더가 에러 내용 함께 읽음 |
| `<div id="usernameError">` | `role="alert"` | 에러 표시 시 스크린리더가 즉시 읽어줌 |
| `<input id="password">` | `aria-describedby="passwordError"` | 동일 |
| `<div id="passwordError">` | `role="alert"` | 동일 |

**검증:**
- `role="alert"` → `aria-live="assertive"` 와 동일 효과. 에러 텍스트가 DOM에 삽입되는 순간 스크린리더 즉시 낭독 ✅
- `aria-describedby` → input에 포커스가 있을 때 현재 에러 메시지도 함께 읽힘 ✅
- 두 속성 세트가 표준 ARIA 패턴 (input + linked error div) ✅

---

## 9. 잘 구현된 부분 (유지)

- **이중 유효성 검사 구조**: 클라이언트(JS) + 서버(serializers.py) 동일 규칙 적용 — 클라이언트 우회 시도 방어
- **에러 메시지 일치**: 프론트-백엔드 에러 문자열이 완전히 동일 — 사용자 혼란 없음
- **clear 버튼 완결성**: 삭제 + 포커스 복귀 + 에러 초기화 3가지를 동시에 처리
- **두 필드 동시 에러 표시**: 한 필드에서 막지 않고 두 필드 모두 검사 — 사용자가 한 번에 모든 에러 인지 가능
- **입력 시 에러 자동 해제**: input 이벤트에서 에러를 지워 불필요한 에러 잔존 없음
- **label 연결**: `for` 속성으로 input과 label 연결 — 클릭 영역 확대 및 스크린리더 지원
- **autocomplete 설정**: `username`/`current-password` — 브라우저/패스워드매니저 연동
