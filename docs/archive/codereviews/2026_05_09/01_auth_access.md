# 01. 인증/인가 (Auth & Access Control)

## 1. 범위

### 1.1 API 엔드포인트
| URL | 메서드 | 뷰 | 권한 |
|---|---|---|---|
| `/api/auth/login/` | POST | LoginView | AllowAny |
| `/api/auth/me/` | GET | MeView | IsAuthenticated |
| `/api/auth/profile/` | GET | MyProfileView | IsAuthenticated |
| `/api/auth/password/change/` | POST | PasswordChangeView | IsAuthenticated |
| `/api/auth/logout/` | POST | LogoutView | IsAuthenticated |
| `/api/auth/token/refresh/` | POST | TokenRefreshView (simplejwt) | AllowAny |
| `/accounts/login/` | GET | login_page | (페이지) |

### 1.2 백엔드 파일
- [drf-server/apps/accounts/views/auth_views.py](../../../../drf-server/apps/accounts/views/auth_views.py) — 368줄, 5개 뷰 클래스 + `_get_client_ip` 헬퍼
- [drf-server/apps/accounts/serializers/auth_serializers.py](../../../../drf-server/apps/accounts/serializers/auth_serializers.py) — LoginSerializer, MyProfileSerializer, PasswordChangeSerializer
- [drf-server/apps/accounts/urls.py](../../../../drf-server/apps/accounts/urls.py) — 페이지/API 라우팅 분리
- [drf-server/apps/accounts/models/login_log.py](../../../../drf-server/apps/accounts/models/login_log.py) — LoginLog (성공/실패/잠금/비활성/로그아웃)
- [drf-server/apps/core/permissions.py](../../../../drf-server/apps/core/permissions.py) — IsSuperAdmin, IsSuperAdminOrFacilityAdmin
- [drf-server/config/settings.py:140-176](../../../drf-server/config/settings.py#L140-L176) — DRF 인증/JWT/백오피스 URL

### 1.3 프론트엔드 파일
- [drf-server/static/js/auth/login.js](../../../../drf-server/static/js/auth/login.js) — 로그인 폼·검증·토큰 저장
- [drf-server/static/js/shared/auth.js](../../../../drf-server/static/js/shared/auth.js) — 토큰 보관소·apiFetch 래퍼·자동 refresh
- [drf-server/static/js/shared/layout.js:184](../../../../drf-server/static/js/shared/layout.js#L184) — 로그아웃 버튼 핸들러
- [drf-server/static/js/detail/my_profile.js](../../../../drf-server/static/js/detail/my_profile.js) — `/api/auth/profile/`, `/api/auth/password/change/` 소비
- [drf-server/templates/auth/login.html](../../../../drf-server/templates/auth/login.html) — 로그인 페이지 마크업
- [drf-server/templates/components/app_config.html](../../../../drf-server/templates/components/app_config.html) — `window.AppConfig` 주입

## 2. 기능 흐름

### 2.1 로그인 → 토큰 발급 → 대시보드 진입
```
1. 사용자가 /accounts/login/ 진입
2. login.js IIFE 시작 시 Auth.getAccessToken() 존재 확인
   ├─ 있으면 GET /api/auth/me/ 시도
   │   ├─ 200 → /dashboard/ 자동 리다이렉트 (재로그인 생략)
   │   └─ 401 → Auth.clear() 후 폼 노출
   └─ 없으면 폼 노출
3. 폼 submit → 클라이언트 validateUsername/validatePassword 1차 검사
4. POST /api/auth/login/ {username, password}
   └─ LoginView.post:
       ├─ LoginSerializer.is_valid()
       │   ├─ validate(): 잠금/비활성/authenticate 순차 검사
       │   ├─ 실패 시 user_obj.record_failed_login() (5회 누적 → 자동 잠금)
       │   └─ self._login_failure 매직스트링으로 실패 사유 분류
       ├─ 실패 → LoginLog 기록(non_field_errors인 경우만) + 4xx
       └─ 성공 → LoginLog(SUCCESS) + RefreshToken.for_user(user) 발급
5. login.js 응답 200 수신
   ├─ Auth.setTokens({access, refresh, username, role}) → localStorage 저장
   └─ window.location.href = '/dashboard/'
```

### 2.2 인증된 API 호출 (모든 페이지 공통)
```
1. JS: Auth.apiFetch('/api/...')
2. _resolveUrl(url) (window.AppConfig.apiUrl 우선)
3. Authorization: Bearer <access_token> 부착하여 fetch
4. 응답 401:
   ├─ Auth._refresh() — POST /api/auth/token/refresh/
   │   └─ 성공: localStorage.access_token 갱신 후 재시도(1회)
   │   └─ 실패: redirectLogin() → /accounts/login/
   └─ 그 외: 그대로 반환
```

### 2.3 비밀번호 변경
```
1. /dashboard/profile/ 페이지 → my_profile.js
2. 현재/신규/신규확인 입력 → POST /api/auth/password/change/
3. PasswordChangeSerializer.validate():
   ├─ check_password(current) — 현재 비밀번호 검증
   ├─ new != current 검증
   └─ new == new_confirm 검증
4. user.set_password() + save(update_fields=["password","updated_at"]) → {ok: true}
```

### 2.4 로그아웃
```
1. layout.js (사이드바·헤더) → POST /api/auth/logout/
2. LogoutView.post:
   ├─ LoginLog(LOGOUT) 기록
   └─ request.session.flush() (Django 세션 초기화 — JWT는 stateless라 별도 처리)
3. JS는 Auth.clear() + redirectLogin()
   ※ 서버 측에서는 access/refresh 토큰을 폐기하지 않음 (블랙리스트 미설정)
```

## 3. 백엔드 소견

### 3.1 일반 코드 리뷰
- **[중] 매직스트링 매칭의 fragile한 실패 분류**
  [auth_serializers.py:54,61,75](../../../../drf-server/apps/accounts/serializers/auth_serializers.py#L54)에서 `self._login_failure = "failed_locked"` 등 raw 문자열 사용. 한편 [auth_views.py:118](../../../../drf-server/apps/accounts/views/auth_views.py#L118)은 `LoginLog.LoginResult.FAILED_PASSWORD` 기본값으로 fallback. serializer는 enum이 아닌 string으로 셋하고 view는 enum과 비교 — 두 enum의 값이 정확히 매칭한다는 암묵적 contract. `LoginLog.LoginResult`를 직접 import해 enum으로 셋하거나, serializer가 dict를 반환하도록 변경 권장.
- **[중] 광범위한 except**
  [auth_views.py:121-126](../../../../drf-server/apps/accounts/views/auth_views.py#L121-L126) `try ... except Exception`으로 user 조회 실패를 묵살. `User.DoesNotExist` 정도만 잡는 게 명확 (지금은 DB 장애도 감춤).
- **[하] LoginLog 직접 ORM 호출이 view에 산재**
  성공·실패·로그아웃 3곳에서 view가 직접 `LoginLog.objects.create()`. 추후 비동기 기록·감사 로그 정책 변경 시 변경 지점이 분산. `apps/accounts/services/login_log.py` 신설 권장 (현재 services 폴더는 빈 패키지).
- **[하] inline_serializer/extend_schema 길어서 가독성 저하**
  스키마 정의가 view 본문보다 길어짐. 응답 스키마는 `apps/accounts/schemas.py`로 분리 또는 `inline_serializer` 대신 명시 Serializer 클래스 사용 검토.
- **[하] User 재조회 한 번 더**
  [auth_views.py:289-294](../../../../drf-server/apps/accounts/views/auth_views.py#L289) `MyProfileView.get`은 `request.user`가 이미 있는데 `get_user_model().objects.prefetch_related().get(pk=...)`로 다시 조회. select_related 정보가 필요한 거면 `User.objects.with_profile_relations(request.user.pk)` selector 위임 권장.

### 3.2 아키텍처/레이어
- **[중] services 부재**
  CLAUDE.md 컨벤션상 "view는 service만 호출"이지만 `apps/accounts/services/`는 빈 패키지(`__init__.py`만). LoginView 본문에 인증·로깅·잠금 카운터·토큰 발급이 모두 인라인 → `services/auth_service.py::login(username, password, ip, ua) -> LoginResult` 형태로 추출 권장. 테스트 가능성·재사용성 모두 향상.
- **[하] selectors 사용처 한정**
  `selectors/admin_users.py`만 존재 → MeView/MyProfileView가 직접 ORM. 인증 도메인은 `selectors/users.py` 추가 후 view에서 위임 권장.
- **파일 크기**: 368줄 — 200줄+ 임계는 넘지만 단일 도메인(인증)으로 응집도가 있어 시급한 분할은 불필요. service 추출이 일어나면 자연스럽게 200줄 이하로 줄어들 것.

### 3.3 보안 관점 (요약, 상세는 99에 집계)
- **[상] JWT 블랙리스트 미설정**
  [settings.py:163-171](../../../drf-server/config/settings.py#L163-L171)에 `ROTATE_REFRESH_TOKENS`, `BLACKLIST_AFTER_ROTATION` 미설정. LogoutView에서 토큰 폐기 불가 → 탈취된 토큰을 30일간 사용 가능. `simplejwt.token_blacklist` 앱 추가 + `BLACKLIST_AFTER_ROTATION=True` 권장.
- **[상] ACCESS_TOKEN_LIFETIME 24시간**
  기본 24h는 web app으론 긴 편. XSS로 access 토큰 탈취 시 24h 노출. 15~60분으로 줄이고 refresh 회전과 결합 권장. 배포 환경별로 조정 가능하도록 env 변수는 이미 분리되어 있음 → 권장값 변경만 필요.
- **[중] 비밀번호 변경 후 기존 토큰 유효**
  PasswordChangeView가 JWT를 폐기하지 않음. 다른 디바이스/브라우저의 access 토큰이 만료까지 유효 → 정책상 비밀번호 변경 시 본인의 active session 강제 로그아웃 권장 (블랙리스트와 결합 필요).
- **[중] 무한 record_failed_login 호출 시 enumeration 위험**
  존재하지 않는 username을 보내면 `user_obj=None` 분기로 `record_failed_login()` 호출 안 됨. 즉 응답 시간 차이로 username 존재 여부가 새어나갈 가능성 → 동일한 메시지 + 일정한 응답시간 보장 권장(현재 메시지는 통일되어 있음, 시간차만 잠재 위험).
- **[중] X-Forwarded-For 신뢰 가정**
  [auth_views.py:34-39](../../../../drf-server/apps/accounts/views/auth_views.py#L34) `_get_client_ip`가 X-Forwarded-For 우선. 리버스 프록시 앞단이 없으면 클라이언트가 임의 IP로 LoginLog 위조 가능. 운영 환경에서 신뢰할 수 있는 프록시 화이트리스트 또는 Django `USE_X_FORWARDED_HOST`/`SECURE_PROXY_SSL_HEADER`와 병행 검토.

## 4. 프론트엔드(JS/HTML) 소견

### 4.1 백엔드 contract와의 정합성
- **[하] 클라이언트/서버 검증 규칙 듀얼 메인테넌스**
  username 정규식·길이, 비밀번호 8자+2종 정책이 [login.js:95-107](../../../../drf-server/static/js/auth/login.js#L95-L107)와 [auth_serializers.py:23-40](../../../../drf-server/apps/accounts/serializers/auth_serializers.py#L23-L40) 양쪽에 동일 로직으로 존재. 한쪽 정책 변경 시 다른 한쪽 누락 위험. 응답 메시지를 그대로 노출하거나, `app_config.html`에 정책 상수를 주입해 단일 출처화.

### 4.2 토큰 보관/사용
- **[상] localStorage에 access·refresh 토큰 저장**
  XSS 한 번이면 양쪽 토큰 탈취 → 30일 + 24h 동안 임의 호출 가능. httpOnly + Secure + SameSite=Strict 쿠키로 refresh 보관, access는 메모리(SPA의 경우)에 두는 패턴이 권장. 다만 현재 아키텍처(다중 페이지 + 페이지 진입마다 토큰 필요)에서는 정착 비용이 큼 → 최소한 CSP 헤더 + 외부 스크립트 호스팅 금지 + DOMPurify 등 XSS 완화 다층화 필요.
- **[중] _refresh 동시성 보호 부재**
  [auth.js:69-90](../../../../drf-server/static/js/shared/auth.js#L69-L90)에서 401 → `_refresh()` → 재시도 흐름. 페이지가 동시에 다수의 fetch를 발사하면 모두 401 응답을 받아 `_refresh`가 동시 다발로 호출됨. 마지막 _refresh의 access만 유효해 앞선 refresh가 (블랙리스트 활성화 시) 무효화될 수 있음. **싱글톤 in-flight Promise 패턴**(`if(this._refreshing) return this._refreshing;`)으로 중복 호출 방지 권장.

### 4.3 페이지/템플릿
- **[하] CSRF 토큰 미사용**
  [login.html](../../../../drf-server/templates/auth/login.html)에 `{% csrf_token %}` 없음. JWT-only API에선 CSRF 필요 없으나, Django 세션 기반 view가 일부 남아있다면(예: `LogoutView`가 `request.session.flush()` 호출) 정책 일관성 검토 필요. 세션이 실질적으로 사용되지 않는다면 `SESSION_COOKIE_SAMESITE='Lax'` 등 보강.
- **[하] AppConfig.apiUrl 폴백**
  [login.js:126-127](../../../../drf-server/static/js/auth/login.js#L126), [auth.js:42-46](../../../../drf-server/static/js/shared/auth.js#L42)에서 `window.AppConfig` 미정의 시 path 그대로 사용. 정상 흐름이지만, 설정 누락 시 silent fallback이라 디버깅 시 혼란. 적어도 `console.warn` 한 줄.

### 4.4 JS 책임 분리
- **[하] login.js 내 폼 검증 로직 100+줄**
  show/clearFieldError, validateUsername, validatePassword가 login.js에 인라인. 다른 폼(비밀번호 변경, 사용자 등록)에서 동일 패턴 반복 가능성 → `shared/form-validators.js`로 추출 후 username/password 정책 함수만 노출.

## 5. 개선 제안

각 항목 라벨: 우선순위 [상/중/하] · 규모 [소/중/대].

### A1. JWT 블랙리스트 도입 [상 · 중]
- **왜 필요?**: 현재는 로그아웃·비밀번호 변경 후에도 기존 토큰이 그대로 살아있다. 토큰이 탈취되면 access 24시간, refresh 30일 동안 막을 방법이 없다.
- **장점**: 로그아웃·비밀번호 변경 시 즉시 무효화 가능 / refresh 회전(rotation)으로 1회용 보장 / 사고 대응(특정 사용자 강제 로그아웃) 가능.
- **단점**: 인증 시 블랙리스트 조회 1회 추가(DB 인덱스로 미미) / `token_blacklist` 앱 마이그레이션·정기 정리 필요.
- **변경 위치**: `INSTALLED_APPS`에 `rest_framework_simplejwt.token_blacklist` 추가, `SIMPLE_JWT`에 `ROTATE_REFRESH_TOKENS=True`/`BLACKLIST_AFTER_ROTATION=True`, [LogoutView](../../../../drf-server/apps/accounts/views/auth_views.py#L334)·[PasswordChangeView](../../../../drf-server/apps/accounts/views/auth_views.py#L298)에서 `RefreshToken(refresh).blacklist()` 호출.

### A2. ACCESS_TOKEN_LIFETIME 단축 [상 · 소]
- **왜 필요?**: 24시간은 일반적인 web app 기준으로 매우 길다. XSS 한 번이면 24시간 동안 사용자를 가장할 수 있다.
- **장점**: 토큰 탈취 노출 시간 95% 감소(24h→1h) / refresh 토큰 회전과 시너지.
- **단점**: refresh 호출 빈도 증가(50배) — 하지만 DB 부하는 미미.
- **변경 위치**: [settings.py:164](../../../drf-server/config/settings.py#L164) default `hours=24` → `minutes=60`. env 변수는 이미 분리되어 있어 운영별 조정 가능.

### A3. JS `_refresh` 동시성 보호 [상 · 소]
- **왜 필요?**: 페이지 진입 시 여러 fetch가 동시에 401을 받으면 `_refresh`가 다수 호출된다. A1 도입(refresh 회전) 후엔 가장 마지막 refresh만 유효해 앞의 fetch들이 무효 토큰으로 재시도 → 강제 로그아웃되는 회귀 버그 가능.
- **장점**: 동시 다발 요청 안전 / refresh 호출 1회로 최소화.
- **단점**: 코드 한 줄짜리 `_refreshing` Promise 캐시 추가뿐 — 사실상 무비용.
- **변경 위치**: [auth.js:48-65](../../../../drf-server/static/js/shared/auth.js#L48-L65) `_refresh()` 시작 시 `if(this._refreshing) return this._refreshing;` 가드.

### A4. accounts services 레이어 신설 [중 · 중]
- **왜 필요?**: CLAUDE.md는 "view는 service만 호출"인데 LoginView 본문에 인증·LoginLog·잠금카운터·토큰발급이 인라인. 같은 로직을 추후 CLI/배치/관리자 강제로그인에서 재사용할 수 없다.
- **장점**: 단위 테스트 용이(view 우회) / 정책 변경 한 군데서 / Phase 1~4 컨벤션 준수.
- **단점**: 파일 1개 추가·import 변경 / 단기적 PR 라인수 증가.
- **변경 위치**: 신규 [apps/accounts/services/auth_service.py](../../../../drf-server/apps/accounts/services/) (`login()`, `logout()`, `change_password()`), view 5개 본문은 service 호출 + 응답 직렬화로 축소.

### A5. `_login_failure` 매직스트링 → enum [중 · 소]
- **왜 필요?**: serializer는 `"failed_locked"` 문자열, view는 `LoginLog.LoginResult.FAILED_PASSWORD` enum과 비교. enum 값이 바뀌면 silent 미스매치 → LoginLog에 잘못된 라벨 기록.
- **장점**: 타입 안전 / IDE 리네임 안전.
- **단점**: serializer가 model을 import (단방향 의존, 큰 문제 아님).
- **변경 위치**: [auth_serializers.py:54,61,75](../../../../drf-server/apps/accounts/serializers/auth_serializers.py#L54).

### A6. X-Forwarded-For 신뢰 정책 명시 [중 · 소]
- **왜 필요?**: 리버스 프록시 앞단이 없는 환경(개발·일부 배포)에서 클라이언트가 임의 IP를 헤더에 넣어 LoginLog를 위조할 수 있다. 감사 로그가 신뢰 불가능해진다.
- **장점**: 운영팀이 설정 의도를 명확히 알 수 있음 / 배포 설정 누락으로 인한 위변조 차단.
- **단점**: 배포 환경별로 환경변수 1개 추가.
- **변경 위치**: settings.py에 `TRUSTED_PROXY_IPS` env 추가, [_get_client_ip](../../../../drf-server/apps/accounts/views/auth_views.py#L34)가 REMOTE_ADDR이 신뢰 목록에 있을 때만 X-Forwarded-For 사용.

### A7. 검증 정책 단일 출처화 [하 · 중]
- **왜 필요?**: username/password 정책이 JS와 Python 양쪽에 동일 로직으로 존재. 정책 변경 시 한쪽 누락 가능.
- **장점**: 이중 메인테넌스 제거.
- **단점**: 단순 변경(20줄)을 메타데이터화하면 오히려 복잡도 증가 가능 — 정책 변경 빈도가 낮으면 비용 대비 이득 적음.
- **변경 위치**: [shared/form-validators.js](../../../../drf-server/static/js/shared/) 신규, login.js·my_profile.js에서 import. 또는 `app_config.html`에 정책 상수 주입.

### A8. login_log 헬퍼 추출 [하 · 소]
- **왜 필요?**: `LoginLog.objects.create()`가 view 3곳에 반복. 추후 비동기 기록·외부 SIEM 전송 시 변경 지점 분산.
- **장점**: 변경 1군데 / 감사 정책 추가 용이.
- **단점**: 별 거 아님.
- **변경 위치**: [services/login_log.py](../../../../drf-server/apps/accounts/services/) 신규 (`record_login_event(user, result, ip, ua)`).

### A9. MyProfileView 재조회 제거 [하 · 소]
- **왜 필요?**: `request.user`가 이미 있는데 `User.objects.prefetch_related().get(pk=...)`로 다시 조회 → 쿼리 1회 낭비.
- **장점**: 쿼리 절감(미미).
- **단점**: 없음.
- **변경 위치**: [auth_views.py:289](../../../../drf-server/apps/accounts/views/auth_views.py#L289).

### A10. OpenAPI 스키마 분리 [하 · 중]
- **왜 필요?**: `extend_schema` 데코레이터가 view 본문보다 길다. 가독성 저하.
- **장점**: view 가독성 향상 / 스키마 재사용.
- **단점**: 신규 파일·import 1개 / 디버깅 시 점프 1번 더.
- **변경 위치**: [apps/accounts/schemas.py](../../../../drf-server/apps/accounts/) 신규.

## 6. 구현 추천 순서

작업 의존성과 위험도를 고려한 단계별 권장 순서. **각 단계는 별도 PR로** 분리해 회귀 리스크 최소화.

### 1단계 — 즉시 적용 (1일 내, 보안 시급) ⚡
- **A2** ACCESS_TOKEN_LIFETIME 24h→1h: env 한 줄 변경, 무손실
- **A3** `_refresh` 동시성 가드: JS 한 파일, 즉시 효과
- **이유**: 코드 변경 최소·회귀 거의 없음·보안 효과 즉시. A1 도입 전이라도 단독으로 가치.

### 2단계 — 토큰 보안 강화 (1주 내) 🔐
- **A1** JWT 블랙리스트 도입 + 로그아웃·비번변경 시 refresh 블랙리스트
- **이유**: A2와 결합해야 효과 극대화 (짧은 access + 회전·블랙리스트된 refresh). 마이그레이션 1회 + 인증 미들웨어 영향 → 충분한 테스트 필요.

### 3단계 — 아키텍처 정리 (다음 sprint) 🏗
- **A4** services 레이어 신설
- **A5** 매직스트링 → enum (A4 작업 중 같이)
- **A8** login_log 헬퍼 (A4 작업 중 같이)
- **이유**: 컨벤션 정합·테스트 가능성. A1·A2·A3가 검증된 후 안정된 환경에서 리팩토링.

### 4단계 — 운영·UX 개선 (여유 시) ✨
- **A6** X-Forwarded-For 신뢰 정책
- **A9** MyProfileView 재조회 제거
- **A7** 검증 정책 단일 출처화 (정책 변경 빈도 낮으면 보류 가능)
- **A10** OpenAPI 스키마 분리

### ⚠️ 주의사항 (초보자용)
- **A1 도입 시 마이그레이션 누락 주의**: `python manage.py migrate token_blacklist` 필수. 기존 발급된 refresh 토큰은 자동 무효화되지 않음 → 모든 사용자 재로그인 필요할 수 있음 (배포 공지 필요).
- **A2의 1시간**도 아직 길다는 의견이 있음. 운영에서 사용성 확인 후 30분~15분으로 단계적 단축 권장.
- **A3**은 가장 안전하고 효과 큰 변경 — 가장 먼저 적용해도 좋음.
