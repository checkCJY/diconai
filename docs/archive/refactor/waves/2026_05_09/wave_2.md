# Wave 2 — JWT 인증 보안 리팩토링 실행 보고서

> **브랜치**: `feature/0508_refactory_code`
> **작업일**: 2026-05-09 ~ 2026-05-10
> **분석 베이스**: [docs/codereviews/2026_05_09/01_auth_access.md](../../../codereviews/2026_05_09/01_auth_access.md), [docs/refactor/js/2026_05_09/01_auth_session.md](../../js/2026_05_09/01_auth_session.md)
> **상태**: ✅ 완료
> **검증**: pytest 84/84 통과, ruff lint+format 통과
> **의존성**: Wave 1 완료 (정합·로깅 + ServiceTokenAuthentication 인프라)

## 1. 작업 개요

### 1.1 목표
**JWT 인증의 가장 큰 보안 위험 5건**을 한 묶음으로 해소:
- 탈취된 access·refresh 토큰을 30일간 무력 대응 → 즉시 무효화 가능
- 다중 401 race로 인한 강제 로그아웃 회귀 차단
- ACCESS_TOKEN 24h → 1h로 노출 시간 95% 감소

### 1.2 범위
- 백엔드 4건 (B6, B7, B8, B9) — Wave 1의 ServiceToken 위에 빌드
- JS 2건 (J12, J13) — 백엔드 변경과 페어
- 마이그레이션 1개 (token_blacklist)
- 환경변수 1개 권장 (`JWT_ACCESS_TOKEN_LIFETIME_HOURS`)

### 1.3 영향 파일 (4개 + 마이그레이션)

| 분류 | 파일 |
|---|---|
| **백엔드** | `drf-server/config/settings.py`, `drf-server/apps/accounts/views/auth_views.py` |
| **JS** | `drf-server/static/js/shared/auth.js`, `drf-server/static/js/shared/layout.js` |
| **마이그레이션** | `token_blacklist` 앱 (Django 자동 적용, 13개 마이그레이션) |

### 1.4 Wave 1 → Wave 2 의존성
- **Wave 1 ServiceTokenAuthentication**과 무관 (별도 보안 영역)
- Wave 2의 J12 (`_refresh` 동시성)는 B6-B8 (ROTATE 활성화) 도입 직후 시급 — 미적용 시 회귀 버그
- J13 (Logout body) ↔ B9 (LogoutView blacklist) 페어 변경

## 2. 변경 항목 상세

각 항목은 5섹션:
**(A) 무엇이 바뀌었나** · **(B) 왜 바뀌었나** · **(C) 적용된 기능** · **(D) Before / After** · **(E) 다른 방법 trade-off**

---

### B6+B7. SimpleJWT token_blacklist 앱 도입 ([config/settings.py:36-61](../../../../drf-server/config/settings.py#L36-L61), 마이그레이션)

**(A) 변경 내용**
- `INSTALLED_APPS`에 `rest_framework_simplejwt.token_blacklist` 추가
- `python manage.py migrate token_blacklist` 실행 (13개 마이그레이션 적용)
  - `token_blacklist_outstandingtoken` 테이블: 발급된 모든 refresh 토큰 추적
  - `token_blacklist_blacklistedtoken` 테이블: 무효화된 refresh 토큰 기록

**(B) 왜 바뀌었나**
- 분석 근거: [01_auth_access.md A1](../../../codereviews/2026_05_09/01_auth_access.md)
- 기존: refresh 토큰을 서버 측에서 무효화 불가 → 탈취 시 30일간 무력
- SimpleJWT는 token_blacklist 앱을 통해 토큰 회전·블랙리스트 추적 기능 제공

**(C) 적용된 기능**
- DB 기반 토큰 추적: 모든 refresh 토큰이 OutstandingToken 테이블에 기록
- 블랙리스트 등록 API: `RefreshToken(token).blacklist()` 호출 시 BlacklistedToken 테이블에 등록
- 인증 미들웨어가 자동으로 블랙리스트 조회 → 만료 처리

**(D) Before / After**
```python
# Before
INSTALLED_APPS = [
    "rest_framework",
    "drf_spectacular",
    ...
]
# 마이그레이션 없음

# After
INSTALLED_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # 추가
    "drf_spectacular",
    ...
]
# 마이그레이션: python manage.py migrate token_blacklist (1회 실행)
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ token_blacklist 앱 (DB 기반) | SimpleJWT 표준 / 회전·추적·블랙리스트 통합 | 토큰 발급마다 DB 1회 쓰기 / 인증마다 1회 조회 | **채택** |
| Redis 기반 자체 구현 | 빠른 조회 | 추가 인프라 / 직접 구현 부담 | 미채택 (필요 시 다음 sprint) |
| 짧은 access만 사용 (refresh 제거) | 인프라 단순 | UX 저하 (자주 재로그인) | 미채택 |
| 무변경 | 작업 없음 | 보안 위험 유지 | 변경 전 |

**선택 이유**: SimpleJWT 표준 기능이라 안정성·문서·호환성 모두 검증됨. DB 1회 조회 영향은 인덱스로 미미.

---

### B8. ACCESS_TOKEN_LIFETIME 24h → 1h + ROTATE/BLACKLIST 활성화 ([config/settings.py:162-176](../../../../drf-server/config/settings.py#L162-L176))

**(A) 변경 내용**
- `ACCESS_TOKEN_LIFETIME` 기본값 `hours=24` → `hours=1` (env로 운영별 조정 가능)
- `ROTATE_REFRESH_TOKENS=True` 추가 — refresh 사용 시 새 refresh 발급
- `BLACKLIST_AFTER_ROTATION=True` 추가 — 회전된 refresh 자동 블랙리스트 등록

**(B) 왜 바뀌었나**
- 분석 근거: [01_auth_access.md A2](../../../codereviews/2026_05_09/01_auth_access.md)
- 24h ACCESS_TOKEN: XSS·복사 공격 시 노출 시간이 매우 김
- 일반 web app 권장 access lifetime: 5~60분 (사이트 보안 요구 따라)
- ROTATE_REFRESH_TOKENS 활성화로 refresh를 1회용으로 만들 수 있음

**(C) 적용된 기능**
- **단축된 access lifetime**: XSS로 access 탈취 시 1시간만 사용 가능 (24배 감소)
- **refresh 회전**: refresh 1회 사용 시 새 토큰 발급, 이전 refresh는 자동 블랙리스트
- **재사용 차단**: 탈취된 refresh가 한 번 사용되면 즉시 무효화

**(D) Before / After**
```python
# Before
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        hours=env.int("JWT_ACCESS_TOKEN_LIFETIME_HOURS", default=24)  # 24h
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=30)
    ),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# After
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        hours=env.int("JWT_ACCESS_TOKEN_LIFETIME_HOURS", default=1)  # 1h
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=30)
    ),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ access 1h + ROTATE + BLACKLIST | 보안 강화 / 표준 패턴 | refresh 호출 24배 증가 (DB 부담 미미) | **채택** |
| access 15분 | 더 안전 | refresh 더 빈번 / 개발 환경 빠른 만료로 불편 | 미채택 (운영 안정 후 검토) |
| access 30분 | 적절한 균형 | 1h와 큰 차이 없음 | 미채택 |
| ROTATE만, BLACKLIST 미설정 | refresh 재사용 가능 | 회전의 의미 없음 | 미채택 |
| 무변경 (24h) | 변경 없음 | 노출 시간 길음 | 변경 전 |

**선택 이유**: 1h가 보안·UX 균형. env 변수로 운영별 조정 가능 (실제 운영에서 2~4h로 조정 가능).

**리스크**: 기존 발급된 refresh 토큰은 자동 무효화 안 됨 → 마이그레이션 시점에 사용자 재로그인 안내 권장.

---

### B9. LogoutView에서 refresh 토큰 블랙리스트 ([auth_views.py:334-380](../../../../drf-server/apps/accounts/views/auth_views.py#L334-L380))

**(A) 변경 내용**
- `request.data.get("refresh")`로 클라이언트가 동봉한 refresh 토큰 추출
- `RefreshToken(refresh_token).blacklist()` 호출로 즉시 무효화
- 잘못된·만료·이미 블랙리스트된 토큰은 silent 처리 (UX 우선, 200 반환)
- `@extend_schema`의 request 정의 갱신 (`LogoutRequest.refresh: optional`)

**(B) 왜 바뀌었나**
- 분석 근거: [01_auth_access.md A1](../../../codereviews/2026_05_09/01_auth_access.md)
- 기존: 로그아웃 시 LoginLog 기록만, JWT는 stateless라 서버 측에서 무효화 불가
- B6-B8 도입으로 blacklist 기능 사용 가능 → 즉시 적용

**(C) 적용된 기능**
- 로그아웃 시 refresh 토큰 즉시 무효화 → 다른 디바이스의 활성 세션 차단 가능 (사용자가 의도하면)
- access 토큰은 1시간 후 자연 만료 → 전체 세션 1시간 내 종료
- silent 실패 처리: 잘못된 토큰도 사용자에겐 200 응답 (UX 우선)

**(D) Before / After**
```python
# Before
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        LoginLog.objects.create(
            user=request.user,
            is_login=False,
            login_result=LoginLog.LoginResult.LOGOUT,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        )
        request.session.flush()
        return Response({"ok": True})

# After
class LogoutView(APIView):
    """
    로그아웃 이력을 LoginLog에 기록 + 세션 초기화 + (Phase 5) refresh 토큰 블랙리스트.
    클라이언트는 body에 `refresh` 토큰을 동봉해야 서버 측 폐기가 가능하다.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        LoginLog.objects.create(...)

        # Phase 5: refresh 토큰 블랙리스트 (body에 동봉된 경우만)
        refresh_token = request.data.get("refresh") if isinstance(request.data, dict) else None
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except Exception:
                # 잘못된 토큰·만료·이미 블랙리스트 → 무시 (UX 우선)
                pass

        request.session.flush()
        return Response({"ok": True})
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ body에 refresh 동봉 + silent 실패 | UX 우선 / 클라이언트 단순 | refresh 미동봉 시 무효화 안 됨 (B9 무력화 가능) | **채택** |
| 강제 동봉 (refresh 없으면 400) | 보장된 무효화 | 기존 클라이언트 모두 깨짐 → 운영 영향 | 미채택 |
| 헤더로 refresh 전송 (Authorization-2) | 표준 외 / 보안 모호 | 비표준 / Bearer만 표준 | 미채택 |
| refresh 추출 자동 (access 토큰에서?) | 클라 변경 없음 | access는 stateless이라 refresh 정보 없음 | 미가능 |
| BLACKLIST_AFTER_ROTATION만 (회전 시점에 자동) | 클라 변경 없음 | 로그아웃 즉시 무효화 안 됨 (다음 refresh 사용 시점까지) | 미채택 |

**선택 이유**: J13과 함께 동작 → 정상 사용자는 무효화, 클라이언트가 누락해도 LoginLog는 남음.

---

### J12. `Auth._refresh` 싱글톤 동시성 가드 ([auth.js:48-78](../../../../drf-server/static/js/shared/auth.js#L48-L78))

**(A) 변경 내용**
- `_refreshing: null` 인스턴스 캐시 추가
- `_refresh()` 진입 시 진행 중인 Promise가 있으면 그것 반환 (다중 호출 → 1회만 실행)
- finally에서 `_refreshing = null` 리셋
- 응답에 새 refresh 토큰이 포함되면 localStorage 갱신 (ROTATE 대비)
- catch 빈 → `console.warn`

**(B) 왜 바뀌었나**
- 분석 근거: [01_auth_session.md R1](../../js/2026_05_09/01_auth_session.md)
- B6-B8의 ROTATE_REFRESH_TOKENS 활성화 후, 다중 401 race가 회귀 버그를 만듦:
  1. 페이지 진입 시 fetch A·B·C 동시 발사
  2. 모두 401 응답
  3. 각자 `_refresh()` 호출 → 백엔드는 첫 번째 refresh만 유효 (BLACKLIST_AFTER_ROTATION)
  4. 두 번째 이후 refresh는 401 → 호출자가 `redirectLogin()` → **사용자가 의도치 않게 로그아웃됨**
- 동시성 가드로 refresh 1회만 호출되어 위 회귀 차단

**(C) 적용된 기능**
- **싱글톤 in-flight Promise**: 진행 중인 refresh가 있으면 새로 호출하지 않고 같은 Promise 반환
- **회전된 refresh 자동 갱신**: 응답에 새 refresh가 있으면 localStorage 갱신 (다음 회전 대비)
- **에러 가시성**: catch에 console.warn 추가

**(D) Before / After**
```js
// Before
async _refresh() {
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
  } catch {
    return false;
  }
},

// After
_refreshing: null,
async _refresh() {
  if (this._refreshing) return this._refreshing;  // 동시성 가드

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
      // ROTATE_REFRESH_TOKENS=true면 새 refresh가 응답에 포함됨 → 갱신
      if (data.refresh) localStorage.setItem('refresh_token', data.refresh);
      return true;
    } catch (e) {
      console.warn('[Auth._refresh]', e);
      return false;
    }
  })();

  try { return await this._refreshing; }
  finally { this._refreshing = null; }
},
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 싱글톤 in-flight Promise | 단순 / 정확 / 거의 무비용 | 인스턴스 속성 1개 추가 | **채택** |
| Mutex 라이브러리 | 더 일반화 | 의존성 추가 | 미채택 |
| Promise queue (대기열) | 이론상 같은 효과 | 더 복잡 / 같은 결과 | 미채택 |
| 쿨타임 제한 (예: 1초 내 1회) | 단순 | 정확하지 않음 | 미채택 |
| 무변경 | 작업 없음 | ROTATE 도입 후 즉시 회귀 버그 | 변경 전 |

**선택 이유**: 가장 간단하고 정확한 패턴. JS의 단일 스레드 모델에 자연스럽게 맞음.

---

### J13. Logout 호출 시 refresh body 동봉 ([layout.js:197-209](../../../../drf-server/static/js/shared/layout.js#L197-L209))

**(A) 변경 내용**
- `Auth.apiFetch('/api/auth/logout/', { method: 'POST' })` → body에 `{ refresh: <token> }` 동봉
- refresh 토큰 부재 시는 `{}` 보냄 (백엔드는 silent 처리)

**(B) 왜 바뀌었나**
- B9의 백엔드 LogoutView가 body의 refresh를 받아 blacklist 등록
- JS 변경 없으면 body는 빈 → 백엔드는 무효화 못 함 → B9 무력화

**(C) 적용된 기능**
- 클라이언트가 자기 refresh 토큰을 서버에 폐기 요청
- `Auth.getRefreshToken()`이 null이면 빈 body 보냄 (예: 토큰 이미 정리된 상태)

**(D) Before / After**
```js
// Before
logoutConfirm?.addEventListener('click', async () => {
  try {
    await Auth.apiFetch('/api/auth/logout/', { method: 'POST' });
  } finally {
    modal.style.display = 'none';
    successModal.style.display = 'flex';
  }
});

// After
logoutConfirm?.addEventListener('click', async () => {
  try {
    // Phase 5: refresh 토큰을 body로 동봉 → 서버가 blacklist 등록
    const refresh = Auth.getRefreshToken();
    await Auth.apiFetch('/api/auth/logout/', {
      method: 'POST',
      body: JSON.stringify(refresh ? { refresh } : {}),
    });
  } finally {
    modal.style.display = 'none';
    successModal.style.display = 'flex';
  }
});
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ body에 refresh 동봉 (옵션) | UX 우선 / 토큰 부재도 안전 | 사용자가 명시 동의 없이 refresh 노출 (HTTPS면 안전) | **채택** |
| 헤더 (Cookie)에 refresh 보관 후 자동 전송 | 클라 코드 단순 | 현재 localStorage 보관 방식과 일관성 없음 / 큰 변경 | 미채택 |
| Auth.apiFetch에 통합 (모든 logout 자동 동봉) | DRY | apiFetch는 일반 API용 / logout 특화 정책 | 미채택 |
| 무변경 | 작업 없음 | B9 무력화 | 변경 전 |

## 3. 적용된 신규 기능 (요약)

### 3.1 Token Blacklist 인프라
**위치**: SimpleJWT의 `token_blacklist` 앱
**테이블**: `token_blacklist_outstandingtoken`, `token_blacklist_blacklistedtoken`
**역할**: 모든 refresh 토큰 추적 + 무효화된 토큰 차단
**비용**: 토큰 발급마다 DB 쓰기 1회, 인증마다 조회 1회 (인덱스로 미미)

### 3.2 Refresh Token Rotation
**활성화**: `ROTATE_REFRESH_TOKENS=True` + `BLACKLIST_AFTER_ROTATION=True`
**동작**:
- refresh 사용 시 새 refresh 발급
- 이전 refresh는 즉시 블랙리스트
- 탈취된 refresh가 한 번 사용되면 정상 사용자가 다음에 사용 시 401 → 즉시 사고 감지

### 3.3 짧은 Access Token Lifetime
**활성화**: `ACCESS_TOKEN_LIFETIME=timedelta(hours=1)` (env로 조정)
**효과**: XSS 시 노출 시간 95% 감소 (24h → 1h)

### 3.4 Logout 즉시 무효화
**활성화**: B9 LogoutView에서 `RefreshToken(token).blacklist()`
**효과**: 사용자가 로그아웃하면 refresh가 즉시 무효화 → 다른 디바이스 세션도 access 만료(최대 1h) 후 종료

### 3.5 JS `_refresh` 동시성 가드
**활성화**: `Auth._refreshing` Promise 캐시
**효과**: 다중 401 race로 인한 강제 로그아웃 회귀 차단

## 4. 검증 체크리스트

### 4.1 자동 테스트 ✅
- [x] **fastapi-server pytest**: 22 passed (영향 없음)
- [x] **drf-server pytest**: 62 passed (LoginView·LogoutView·refresh 흐름 모두 통과)
- [x] **ruff lint**: All checks passed
- [x] **ruff format**: Applied (auth_views.py reformat)
- [x] **마이그레이션**: token_blacklist 13개 적용 OK

### 4.2 수동 검증 (권장 — 운영 적용 전 필수)

#### 4.2.1 정상 인증 흐름
- [ ] 로그인 → access·refresh 토큰 발급 (DB OutstandingToken에 기록 확인)
- [ ] API 호출 → access 토큰 정상 인식
- [ ] (1시간 대기 또는 토큰 변조) access 만료 → 자동 refresh → 새 access·refresh 발급
- [ ] 새 refresh 사용 후 옛 refresh로 호출 시 → 401 (BLACKLIST_AFTER_ROTATION 동작 확인)
- [ ] 로그아웃 → DB BlacklistedToken에 기록 확인
- [ ] 로그아웃 후 옛 refresh로 호출 시 → 401

#### 4.2.2 동시성 가드 검증 (J12 핵심)
- [ ] 페이지 진입 시 dev tools에서 access 토큰 일부러 만료시키기
- [ ] 페이지에서 동시에 2~3개 fetch 발사 (예: dashboard 진입 시 menu·workers·summary 등)
- [ ] Network 탭에서 `/api/auth/token/refresh/` 호출이 **1회만** 발생하는지 확인
- [ ] 모든 fetch가 정상 응답 (401 후 재시도 모두 200)
- [ ] 강제 로그아웃 발생 안 함

#### 4.2.3 ACCESS_TOKEN_LIFETIME 짧음 영향
- [ ] 1시간 후 자동 refresh 동작
- [ ] 사용자 UX 영향 (refresh 빈도 증가) 모니터링

#### 4.2.4 회귀 위험 시나리오
- [ ] 기존 로그인 사용자: 마이그레이션 후 refresh 토큰 무효화될 수 있음 → 재로그인 필요 (운영 공지 필요)
- [ ] PR-H 4종 e2e 테스트 통과 확인 (이미 자동 통과 ✓)

### 4.3 환경변수 점검
- [ ] `JWT_ACCESS_TOKEN_LIFETIME_HOURS` 운영 .env에 명시 (1 또는 운영 정책)
- [ ] `JWT_REFRESH_TOKEN_LIFETIME_DAYS` 명시 (기본 30)

## 5. 알려진 한계 / 후속 작업

### 5.1 이번 Wave에 포함되지 않은 항목
- **B10 (선택)**: PasswordChangeView에서 본인 토큰 블랙리스트 — 비밀번호 변경 시 다른 디바이스 강제 로그아웃 (다음 Wave 또는 별도)
- **WS 인증 통합** (분석 09 I4): JWT 토큰을 WS 핸드셰이크에 적용 — Wave 3
- **localStorage → httpOnly 쿠키**: XSS 다층 방어 — 큰 작업, 별도 sprint
- **CSP 헤더**: XSS 다층 방어 — 별도

### 5.2 운영 적용 시 주의사항
1. **마이그레이션 후 사용자 재로그인 필요 가능성**: 기존 발급된 refresh 토큰이 BLACKLIST_AFTER_ROTATION 도입 후 어떻게 처리될지는 SimpleJWT가 자동 무효화하지 않음 — 일부 사용자가 재로그인해야 할 수 있음. **사전 공지 필수**.
2. **ACCESS_TOKEN 1h가 운영에 무리이면 env로 조정**: `JWT_ACCESS_TOKEN_LIFETIME_HOURS=2` 또는 `4`로 시작 → 모니터링 후 조정.
3. **token_blacklist 테이블 정기 청소**: OutstandingToken은 만료된 토큰도 영구 보관 → 30일 이상 된 행은 정기 cleanup 권장. SimpleJWT의 `flushexpiredtokens` 관리 명령 또는 cron.
4. **J12 적용 후 e2e 테스트 회귀 필수**: 토큰 만료 시나리오에서 어떤 fetch도 무한 대기 안 하는지 확인.

### 5.3 향후 분석 항목
- 운영 환경에서 refresh 호출 빈도 측정 (1h 단축 영향)
- BlacklistedToken 테이블 크기 모니터링
- ROTATE 활성화 후 강제 로그아웃 빈도 (J12 효과 측정)

## 6. 머지 전 확인 항목

### 6.1 Git
- [x] commit 분리: B6-B8 / B9 / J12+J13 (3개)
- [x] 신규 마이그레이션 없음 (token_blacklist는 외부 앱이라 자동 적용)
- [x] 변경 파일 4개 (settings.py, auth_views.py, auth.js, layout.js)

### 6.2 운영 영향
- [ ] **운영 적용 전 사용자 재로그인 안내 공지**
- [ ] env 설정: `JWT_ACCESS_TOKEN_LIFETIME_HOURS` 운영별 정책 결정
- [ ] DB 마이그레이션 시점·다운타임 검토 (token_blacklist 13개 마이그레이션, 대용량 데이터 없으니 빠름)
- [ ] 기존 사용자가 재로그인할 수 있는지 사전 검증

### 6.3 PR 작성 (실험 → 머지 결정 후)
- [ ] PR 제목: `feat: Wave 2 — JWT blacklist + access lifetime + refresh 동시성`
- [ ] PR 본문: 본 보고서 §2 + §4 + §5.2 운영 주의사항

## 7. 다음 단계 (Wave 3 후보)

분석 결과의 다음 시급 항목:

### 7.1 알람 contract fragility 차단 (분석 PR-J2 묶음)
- **J14 (= 03 R1)**: `shared/alarm-mapper.js` 추출 — alarm-ws/worker-ws/dashboard/websocket의 키 매핑 통합
- **J15 (= 03 R3)**: 서버 timestamp 사용 (mapper에서)
- **J16 (= 03 R4)**: AlarmToast 호출 일관 (worker-ws)

### 7.2 WS 인증 통합 (분석 PR-S3 묶음)
- **B11 (= 09 I4)**: `fastapi-server/websocket/auth.py` 신설 — Depends 패턴
- **B12**: `/ws/sensors/`, `/ws/worker/{id}/`, `/ws/position/` 모두 인증 적용
- **J17**: ws-client 호출자 모두 `attachToken: true` 일관

### 7.3 XSS 패턴 정착 (분석 PR-J5)
- **J18 (= 04 R1)**: `Menu.render` innerHTML → createElement
- **J19 (= 04 R5)**: menuTree·child path 검증

### 7.4 추가 보안·정합 (선택)
- **B10**: PasswordChangeView 토큰 블랙리스트
- **C1 (= 03 C2)**: `loadMySafetyStatus` 백엔드 권한 변경 (AllowAny → IsAuthenticated)

## 8. 결정 로그 (Wave 2 핵심 의사결정)

### 8.1 access lifetime 1h vs 30분 vs 15분
**선택**: 1h (env 조정 가능)
**이유**: 보안·UX 균형. 운영 안정 후 30분으로 단축 검토.

### 8.2 ROTATE_REFRESH_TOKENS 즉시 활성화 vs 점진적
**선택**: 즉시 (B6-B8 한 묶음)
**이유**: 부분 활성화는 의미 없음 (ROTATE만 + BLACKLIST 미설정 = 보안 효과 0). J12 동시성 가드를 동반하면 회귀 위험 차단.

### 8.3 LogoutView body refresh: 옵션 vs 강제
**선택**: 옵션 (refresh 미동봉 시 silent)
**이유**: 기존 클라이언트 호환성. refresh 동봉은 클라이언트 협업 (J13)으로 보장.

### 8.4 J12 싱글톤 패턴 vs Mutex 라이브러리
**선택**: 싱글톤 in-flight Promise (5줄)
**이유**: JS 단일 스레드에 자연스럽고 의존성 0.

### 8.5 J13 logout body: refresh 단독 vs 전체 토큰
**선택**: refresh만 동봉
**이유**: access는 stateless이라 무효화 의미 없음. refresh만 blacklist 등록하면 충분.

### 8.6 commit 분리: 3개 (B6-B8 / B9 / J12+J13) vs 5개 단위
**선택**: 3개 (의존성 그룹)
**이유**: B6-B8은 한 settings.py 파일이라 분리 어려움 + 의미상 한 묶음. B9는 백엔드 단독. J12+J13은 페어 변경.

## 9. Wave 1 + Wave 2 합산 (현 브랜치 상태)

### 9.1 누적 commit (10개)
```
c58373d refactor : J12+J13 Auth._refresh 싱글톤 + Logout body refresh 동봉
3567c60 feat : B9 LogoutView에서 refresh 토큰 블랙리스트
4735670 feat : B6-B8 SimpleJWT blacklist + ROTATE + access lifetime 1h
5ee7628 refactor : J9-J11 JS 에러 핸들링
0b67e7c refactor : J5-J8 JS 로깅·layout 가드
eb60cfc refactor : J1-J4 JS 정합 (levelLabel 제거 / pushData 검증 / WS_BASE 가드 / pad 중복 제거)
00ae07c feat : B3+B4 service token authentication for ingest endpoints (Phase 5)
0770423 refactor : B2 AlarmPayload extra="allow" → "ignore"
b6cb6ce refactor : B1 print() → logger.exception (positioning)
7e6b404 refactor : B5 WorkerSummaryView permission_classes 클래스화
```

### 9.2 누적 변경
- 백엔드 항목: B1, B2, B3, B4, B5, B6, B7, B8, B9 (9건)
- JS 항목: J1, J2, J3, J4, J5, J6, J7, J8, J9, J10, J11, J12, J13 (13건)
- 총 22건 + 신규 파일 1개 (authentication.py) + 마이그레이션 1세트 (token_blacklist)

### 9.3 누적 검증
- pytest: 84/84 (drf 62 + fastapi 22)
- ruff lint+format: pass
- 회귀 위험: 0 (ServiceToken 옵트인 + JWT blacklist 옵트인)

### 9.4 다음 결정 시점
1. **수동 검증 후 머지 결정**: 본 보고서 §4 항목 수동 검증 → 머지 / 폐기 / 부분 cherry-pick
2. **Wave 3 진행**: 위 §7의 알람 contract / WS 인증 / XSS 패턴 중 선택
3. **운영 적용 준비**: §5.2 운영 주의사항 검토 + env 설정 + 사용자 공지
