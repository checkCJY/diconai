# LG-01 로그인 화면 기본 노출 — 코드 검토 보고서

> 작성자: 한지혜 / 작성일: 2026-04-23
> 대상 기능 ID: **LG-01** (로그인 화면 기본 노출)
> 검토 범위: 프론트엔드 + 백엔드 전체

---

## 1. 기능 정의서 스펙 요약

| 항목 | 내용 |
|------|------|
| 기능 목적 | 서비스 진입 및 인증 시작점 제공 |
| 사용자 시나리오 | 페이지 진입 시 배경, 로고, 플랫폼명, 입력영역, 문의문구 노출 |
| 수집 정보 | 배경 이미지/컬러, 로고, 플랫폼명, 문의 영역 |
| 백엔드 처리 | 기본 설정 및 **문의처 조회 또는 정적 제공** |
| 프론트엔드 처리 | 초기 렌더링, placeholder 기본 상태 노출 |
| 참고사항 | **문의 연락처는 운영 설정값 관리 권장** |

---

## 2. 검토 대상 파일

| 역할 | 파일 경로 |
|------|-----------|
| 화면 템플릿 | `drf-server/templates/auth/login.html` |
| 스타일 | `drf-server/static/css/auth/login.css` |
| 클라이언트 JS (공통 Auth) | `drf-server/static/js/refactors/auth.js` |
| 로그인 API View | `drf-server/apps/accounts/views.py` |
| 로그인 Serializer | `drf-server/apps/accounts/serializers.py` |
| 사용자 모델 | `drf-server/apps/accounts/models/user.py` |
| Django 설정 | `drf-server/config/settings.py` |

---

## 3. 스펙 충족 항목 ✅

| 항목 | 구현 위치 | 비고 |
|------|-----------|------|
| 파란 그라디언트 배경 | `login.css` — `body.login-page` | `#1155a6 → #0d3f82` |
| 로고 영역 | `login.html` — `.login-logo` | SVG 아이콘 + 박스 |
| 플랫폼명 표시 | `login.html` — `.system-name` | "산재 예방 통합 관제 플랫폼" |
| 아이디/비밀번호 입력 필드 | `login.html` — `.form-group` | clear 버튼 포함 |
| 문의 문구 영역 | `login.html` — `.login-footer` | 하단 표시 |
| placeholder 기본 상태 노출 | `login.html` — `placeholder` 속성 | "아이디를 입력하세요" 등 |
| 초기 렌더링 | Django 템플릿 → 서버사이드 렌더링 | 정적 제공 |
| 이미 로그인 시 대시보드 이동 | `login.html` — JS 최상단 | `access_token` 체크 |

---

## 4. 문제 항목 — 심각도별 분류

### 🔴 HIGH — 즉시 수정 필요

---

#### H-1. 문의처 정보 하드코딩 (스펙 직접 위반)

**위치:** `templates/auth/login.html` 59~63줄

```html
<div class="login-footer">
  로그인 관련 문의<br>
  ○○부서 ○○○팀장 000-1234-5678   ← 임시 플레이스홀더 그대로
</div>
```

**스펙 요구사항:**
> "기본 설정 및 문의처 조회 또는 정적 제공" (백엔드 처리)
> "문의 연락처는 운영 설정값 관리 권장" (참고사항)

**문제점:**
- 실제 연락처가 아닌 `○○부서 000-1234-5678` 임시값 그대로 노출
- 운영 중 연락처 변경 시 코드를 직접 수정해야 함
- 스펙이 명시적으로 "설정값 관리 권장"을 요구하고 있으나 미이행

**권장 수정 방향:**
```python
# views.py 또는 settings.py 에서 context로 전달
CONTACT_INFO = env("CONTACT_INFO", default="관리자에게 문의하세요.")
```
```html
<!-- login.html -->
<div class="login-footer">
  로그인 관련 문의<br>
  {{ contact_info }}
</div>
```

---

#### H-2. 계정 잠금 로직 모델에만 있고 실제 미작동 (LG-04 연계)

**위치:** `apps/accounts/serializers.py` 36~47줄 vs `apps/accounts/models/user.py` 80~97줄

**모델에는 구현되어 있지만:**
```python
# user.py — 메서드 존재
def record_failed_login(self, max_attempts=5, lockout_minutes=30): ...
def reset_failed_login(self): ...
@property
def is_locked(self): ...
```

**Serializer에서는 전혀 호출하지 않음:**
```python
# serializers.py validate() — 잠금 체크 없음
def validate(self, attrs):
    user = authenticate(...)
    if not user:
        raise serializers.ValidationError("아이디 또는 비밀번호가 올바르지 않습니다.")
    attrs["user"] = user
    return attrs
```

**문제점:**
- 5회 실패 후 잠금 기능이 있는 것처럼 모델이 구성되어 있으나 **실제로는 아무것도 작동하지 않음**
- `is_locked` 체크가 없어 잠긴 계정도 정상 로그인 가능
- `record_failed_login()` 미호출로 실패 횟수가 쌓이지 않음

**권장 수정 방향:**
```python
# serializers.py
def validate(self, attrs):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user_obj = User.objects.get(username=attrs["username"])
        if user_obj.is_locked:
            raise serializers.ValidationError("계정이 잠겼습니다. 잠시 후 다시 시도해주세요.")
    except User.DoesNotExist:
        pass

    user = authenticate(...)
    if not user:
        # 실패 카운트 증가
        try:
            user_obj = User.objects.get(username=attrs["username"])
            user_obj.record_failed_login()
        except User.DoesNotExist:
            pass
        raise serializers.ValidationError("아이디 또는 비밀번호가 올바르지 않습니다.")

    user.reset_failed_login()
    attrs["user"] = user
    return attrs
```

---

#### H-3. LoginLog 감사 기록 미연동

**위치:** `apps/accounts/views.py` — `LoginView.post()`

**LoginLog 모델은 있지만 뷰에서 저장 코드가 없음:**
```python
# views.py — LoginLog.objects.create() 호출 없음
class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(...)
        ...
        return Response({...})  # 로그 저장 없이 바로 반환
```

**문제점:**
- 로그인 성공/실패 이력 추적 불가
- 보안 감사, 이상 접근 탐지가 실질적으로 작동하지 않음
- 모델을 만든 의도가 사라짐

---

### 🟡 MEDIUM — 운영 전 수정 권장

---

#### M-1. 로고 텍스트 "로고" 하드코딩

**위치:** `templates/auth/login.html` 21줄

```html
<span class="logo-text">로고</span>   ← 개발용 placeholder 잔존
```

실제 서비스 로고 이미지(`<img>`) 또는 정확한 서비스명으로 교체 필요.

---

#### M-2. 플랫폼명 HTML 직접 하드코딩

**위치:** `templates/auth/login.html` 7줄, 23줄

```html
<title>로그인 — 산재 예방 통합 관제 플랫폼</title>
<div class="system-name">산재 예방 통합 관제 플랫폼</div>
```

플랫폼명이 두 곳에 중복으로 하드코딩되어 있어 변경 시 누락 위험 있음.
Django `settings.py`에서 `PLATFORM_NAME`으로 관리하고 template context로 전달 권장.

---

#### M-3. 기존 login.md 문서와 실제 코드 불일치

**위치:** `drf-server/docs/HJH/login.md`

| 항목 | 문서 내용 | 실제 코드 |
|------|-----------|-----------|
| 배경색 | `#1976d2` | `#1155a6` (다름) |
| 입력 필드 수 | 아이디/비밀번호/**비밀번호 확인** 3개 | 아이디/비밀번호 **2개** |
| 로그인 URL | `/` | `/accounts/login/` |
| 오류 표시 위치 | "아이디 필드에 표시" | **서버 오류 박스**에 표시 |

→ 문서가 이전 버전 기준으로 작성되어 현재 코드와 맞지 않음. 팀원에게 혼란 야기 가능.

---

#### M-4. 이미 로그인 상태 체크 시 토큰 유효성 미검증

**위치:** `templates/auth/login.html` 70~73줄

```javascript
if (localStorage.getItem('access_token')) {
    window.location.href = '/dashboard/';  // 만료 토큰도 통과
    return;
}
```

**문제점:**
JWT access token이 만료되어도 localStorage에 키가 있으면 대시보드로 이동.
대시보드에서 API 호출 시 401이 발생하여 다시 로그인 화면으로 돌아오므로 UX 이슈 발생.

**권장 수정 방향:**
`/api/auth/me/` 호출로 토큰 유효성을 먼저 확인 후 리다이렉트.

---

#### M-5. 비밀번호 입력 필드 maxlength 미설정

**위치:** `templates/auth/login.html` 47~48줄

```html
<!-- username에는 maxlength="20" 있음 -->
<input type="text" id="username" ... maxlength="20">

<!-- password에는 maxlength 없음 -->
<input type="password" id="password" ...>
```

비밀번호 최대 길이 제한이 없어 매우 긴 문자열 제출 가능 (서버 부하 위험).
→ `maxlength="100"` 또는 서버 정책에 맞는 값 추가 권장.

---

### 🟢 LOW — 장기 개선 고려

---

#### L-1. JWT 토큰 localStorage 저장 (보안 관행 이슈)

**위치:** `templates/auth/login.html` 175~178줄

```javascript
localStorage.setItem('access_token',  data.access);
localStorage.setItem('refresh_token', data.refresh);
```

localStorage는 XSS(크로스사이트 스크립팅) 공격 시 토큰 탈취 위험이 있음.
**httpOnly 쿠키** 방식이 업계 권장 방식.
단, 현 아키텍처(DRF + 별도 프론트엔드 없음) 변경 비용이 크므로 **팀 협의 후 결정** 권장.

---

#### L-2. SQLite 데이터베이스 사용 (개발 전용)

**위치:** `drf-server/config/settings.py` 97~102줄

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
```

SQLite는 동시 접속에 취약. 운영 배포 전 **PostgreSQL** 또는 **MySQL**로 전환 필요.

---

#### L-3. DEBUG = True 기본값

**위치:** `drf-server/config/settings.py` 29줄

```python
DEBUG = True
```

`.env`에서 `DJANGO_DEBUG=False` 설정 후 배포해야 함. 현재는 에러 트레이스백이 외부에 노출될 수 있음.

---

## 5. 종합 요약

| 구분 | 항목 수 | 항목 |
|------|---------|------|
| ✅ 충족 | 8개 | 배경, 로고영역, 플랫폼명, 입력필드, 문의영역, placeholder, 초기렌더링, 로그인상태체크 |
| 🔴 HIGH | 3개 | H-1 문의처 하드코딩, H-2 잠금 로직 미작동, H-3 LoginLog 미연동 |
| 🟡 MEDIUM | 4개 | M-1 로고텍스트, M-2 플랫폼명, M-3 문서불일치, M-4 만료토큰체크, M-5 maxlength |
| 🟢 LOW | 3개 | L-1 localStorage, L-2 SQLite, L-3 DEBUG |

---

## 6. 수정 우선순위 Action Items

| 순서 | 항목 | 담당 | 예상 공수 |
|------|------|------|-----------|
| 1 | H-2 계정 잠금 로직 Serializer 연동 | 백엔드 | 1h |
| 2 | H-3 LoginView에 LoginLog 저장 추가 | 백엔드 | 30min |
| 3 | H-1 문의처를 settings/DB에서 주입 | 백엔드+프론트 | 1h |
| 4 | M-3 login.md 문서 현행화 | 프론트 | 30min |
| 5 | M-1 로고 텍스트 교체 | 프론트 | 15min |
| 6 | M-4 만료 토큰 체크 로직 개선 | 프론트 | 30min |
| 7 | M-5 비밀번호 maxlength 추가 | 프론트 | 5min |
| 8 | L-2/L-3 운영 배포 전 DB/DEBUG 전환 | DevOps | 배포 시점 |

---

---

## 8. 수정 이력 (2026-04-23)

> 검토 보고서 작성 후 6가지 항목 수정 완료. M-1(로고 텍스트)은 브랜드 확정 전까지 보류.

---

### H-2 수정 — 계정 잠금 로직 Serializer 연동

**수정 파일:** `apps/accounts/serializers.py`

`validate()` 메서드에 3단계 로직 추가:

| 단계 | 추가 내용 |
|------|-----------|
| 인증 전 | `user_obj.is_locked` 체크 → 잠금 시 `"failed_locked"` 에러 반환 |
| 인증 전 | `user_obj.is_active` 체크 → 비활성 시 `"failed_inactive"` 에러 반환 |
| 인증 실패 시 | `user_obj.record_failed_login()` 호출 → 실패 카운터 +1, 5회 도달 시 30분 잠금 |
| 인증 성공 시 | `user.reset_failed_login()` 호출 → 카운터 초기화 |

View에서 LoginLog 결과 구분을 위해 `self._login_failure` 속성으로 실패 유형 전달.

**검증:**
- 잠금 상태(`is_locked`) 체크는 `authenticate()` 호출 전에 수행되므로 잠긴 계정으로 반복 시도해도 카운터 중복 증가 없음
- 존재하지 않는 아이디는 `user_obj = None` → `record_failed_login()` 스킵 → 동일 에러 메시지 반환 (사용자 존재 여부 노출 방지)

---

### H-3 수정 — LoginLog 감사 기록 연동

**수정 파일:** `apps/accounts/views.py`

`LoginView.post()`에 추가:

| 상황 | LoginLog 기록 내용 |
|------|-------------------|
| 로그인 성공 | `is_login=True`, `login_result=SUCCESS` |
| 인증 실패 (잠금/비활성/비밀번호 오류) | `is_login=False`, `login_result=_login_failure 값` |
| 포맷 오류 (아이디·비밀번호 형식) | 로그 기록 안 함 (정상적인 입력 실수) |

`_get_client_ip()` 헬퍼 함수 추가 — `X-Forwarded-For` 우선, 없으면 `REMOTE_ADDR` 사용 (프록시/로드밸런서 환경 대응).

**검증:**
- `LoginLog.save()`는 APPEND-ONLY 정책으로 오버라이드 되어 있어 수정 불가 — 감사 로그 불변성 보장
- `user` FK는 `SET_NULL`이므로 존재하지 않는 아이디 시도 시에도 `user=None`으로 정상 저장됨

---

### H-1 수정 — 문의처 정보를 core/constants.py에서 관리

**수정 파일 3개:**

| 파일 | 변경 내용 |
|------|-----------|
| `apps/core/constants.py` | `CONTACT_INFO = "담당 관리자에게 문의하세요."` 상수 추가 |
| `apps/accounts/urls.py` | `login_page`에서 `{"contact_info": CONTACT_INFO}` context 전달 |
| `templates/auth/login.html` | `○○부서 ○○○팀장 000-1234-5678` → `{{ contact_info }}` 템플릿 변수로 교체 |

**운영 연락처 변경 방법:** `apps/core/constants.py`의 `CONTACT_INFO` 값만 수정하면 됨.

---

### M-4 수정 — 만료 토큰 체크 로직 개선

**수정 파일:** `templates/auth/login.html`

**변경 전:**
```javascript
if (localStorage.getItem('access_token')) {
    window.location.href = '/dashboard/';  // 만료 토큰도 통과
    return;
}
```

**변경 후:**
```javascript
if (localStorage.getItem('access_token')) {
    fetch('/api/auth/me/', { headers: { 'Authorization': 'Bearer ' + ... } })
      .then(res => {
        if (res.ok) {
            window.location.href = '/dashboard/';
        } else {
            // 만료/무효 → 토큰 전체 삭제 후 로그인 화면 유지
            ['access_token', 'refresh_token', 'username', 'role']
                .forEach(k => localStorage.removeItem(k));
        }
      })
      .catch(() => { /* 네트워크 오류 — 로그인 화면 유지 */ });
}
```

`auth.js`의 `Auth.getMe()`를 쓰지 않은 이유: `getMe()`는 401 시 `redirectLogin()`을 호출하는데, 이는 로그인 페이지로 이동하는 코드여서 **현재 페이지(로그인)에서 호출하면 자기 자신으로 리다이렉트하는 불필요한 동작** 발생. 로그인 페이지 전용 인라인 처리로 대신함.

---

### M-5 수정 — 비밀번호 maxlength 추가

**수정 파일:** `templates/auth/login.html`

```html
<!-- 변경 전 -->
<input type="password" ... autocomplete="current-password">

<!-- 변경 후 -->
<input type="password" ... autocomplete="current-password" maxlength="100">
```

---

### M-3 수정 — login.md 문서 현행화

**수정 파일:** `docs/HJH/login.md`

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 배경색 | `#1976d2` | `#1155a6 → #0d3f82` (그라디언트) |
| 입력 필드 수 | 아이디/비밀번호/비밀번호확인 3개 | 아이디/비밀번호 2개 |
| 로그인 URL | `/` | `/accounts/login/` |
| 오류 표시 위치 | 아이디 필드에 표시 | 서버 에러 박스에 표시 |
| 관련 파일 목록 | 3개 | 8개 (실제 연관 파일 전체 반영) |
| 로그인 처리 흐름 | 단순 성공/실패 2단계 | 잠금·비활성·실패카운터 포함 상세 흐름 |

---

## 7. 잘 구현된 부분 (유지)

- **유효성 검사 이중 구조**: 프론트(`login.html` JS) + 백엔드(`serializers.py`) 양쪽에 동일 규칙 적용 — 이중 방어 적절
- **중복 클릭 방지**: `btn.disabled = true` + `'로그인 중...'` 텍스트 전환
- **CSS 변수 활용**: `:root { --bg-blue: ... }` — 컬러 일관성 관리 양호
- **소프트 삭제 정책**: `CustomUser.delete()` 오버라이드로 실수 삭제 완전 차단
- **JWT 인증 구조**: `auth.js`의 `apiFetch()` → `Authorization: Bearer` 자동 주입 — 재사용성 높음
- **에러 메시지 한국어화**: 필드별/서버별 구분된 한국어 메시지
- **Enter 키 지원**: `form.addEventListener('submit')` 방식으로 자동 지원
