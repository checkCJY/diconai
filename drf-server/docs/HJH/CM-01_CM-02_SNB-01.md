# CM-01 / CM-02 / SNB-01 구현 변경 내역

> 작성일: 2026-04-16
> 작업자: 한지혜
> 브랜치: devleop

---

## 개요

로그인 이후 모든 화면에 공통 적용되는 헤더(CM-01 / CM-02)와 좌측 SNB 메뉴(SNB-01)를 구현하였습니다.
JWT 기반 인증 API를 함께 추가하여 사용자 권한에 따라 UI가 동적으로 렌더링됩니다.

---

## 변경 파일 목록

| 구분 | 파일 경로 | 변경 유형 |
|------|-----------|-----------|
| Backend | `apps/accounts/models.py` | 수정 |
| Frontend | `templates/header.html` | 신규 |
| Backend | `apps/accounts/serializers.py` | 신규 |
| Backend | `apps/accounts/views.py` | 신규 |
| Backend | `apps/accounts/urls.py` | 신규 |
| Backend | `apps/accounts/migrations/0004_alter_customuser_user_type.py` | 신규 (자동 생성) |
| Backend | `config/settings.py` | 수정 |
| Backend | `config/urls.py` | 수정 |
| Frontend | `templates/login.html` | 신규 |
| Frontend | `templates/dashboard.html` | 수정 (헤더 블록 분리) |
| Frontend | `static/css/style.css` | 수정 |
| Frontend | `static/js/main.js` | 수정 |

> **추가 수정 (스크린샷 검토 1차 반영, 2026-04-16)**
>
> | 구분 | 파일 경로 | 변경 유형 |
> |------|-----------|-----------|
> | Frontend | `templates/header.html` | 수정 — 🔔 알림 버튼 추가 |
> | Frontend | `static/js/main.js` | 수정 — 알림 배지 업데이트 메서드 추가 |

> **추가 수정 (스크린샷 검토 2차 반영, 2026-04-16)**
>
> | 구분 | 파일 경로 | 변경 유형 |
> |------|-----------|-----------|
> | Frontend | `static/js/main.js` | 수정 — ③ 사용자 표시 형식 변경, `renderUser` 파라미터 정리 |
> | Frontend | `templates/header.html` | 수정 — ⑥ 홈 버튼 이모지 → SVG 아이콘으로 교체 |
> | Frontend | `static/css/style.css` | 수정 — `.icon-btn` SVG 정렬, 서브 페이지 공통 스타일 추가 |
> | Frontend | `templates/safety_checklist.html` | 신규 — 작업 전 안전 확인 임시 페이지 |
> | Backend | `config/urls.py` | 수정 — `/safety/checklist/` URL 추가 |

> **추가 수정 (UI 피드백 반영, 2026-04-16)**
>
> | 구분 | 파일 경로 | 변경 유형 |
> |------|-----------|-----------|
> | Frontend | `templates/header.html` | 수정 — 홈 버튼 SVG 크기 확대 (17→22px), 🔔 알림 버튼 제거 |
> | Frontend | `static/js/main.js` | 수정 — `updateAlarmBadge()` 메서드 및 `alarm_count` 처리 코드 제거 |

> **추가 수정 (④ 관리자 메뉴 버튼 구현, 2026-04-16)**
>
> | 구분 | 파일 경로 | 변경 유형 |
> |------|-----------|-----------|
> | Frontend | `templates/header.html` | 수정 — ④ 관리자 메뉴 버튼 위치·형태 변경 (⚙ 아이콘 → 텍스트 버튼) |
> | Frontend | `static/css/style.css` | 수정 — `.admin-menu-btn` 스타일 추가, `.header-center` 레이아웃 수정 |

> **추가 수정 (로그인 화면 UI 개편, 2026-04-17)**
>
> | 구분 | 파일 경로 | 변경 내용 |
> |------|-----------|-----------|
> | Frontend | `templates/login.html` | 로그인 화면 전면 개편 (디자인 스펙 반영) |
>
> **변경 상세**
>
> | 번호 | 항목 | 변경 전 | 변경 후 |
> |------|------|---------|---------|
> | ① | 배경 | 검정 다크 테마 (`#0d1117`) | 파란색 그라디언트 (`#1155a6` → `#0d3f82`) |
> | ② | 로고 | "LOGO" 텍스트 박스 | "에어위드" 텍스트 + 방패 SVG 아이콘 박스 (반투명 흰색 테두리) |
> | ③ | 플랫폼명 | 산재 예방 통합 관제 **시스템** | 산재 예방 통합 관제 **플랫폼** |
> | ④ | 입력란 | 다크 배경 입력창 | 밝은 카드 위 흰색 입력창, 포커스 시 파란 테두리+그림자 효과 |
> | ⑤ | 로그인 버튼 | 파란 버튼 (기존 유지) | 동일 기능 유지, 스타일 정돈 |
> | ⑥ | 문의 문구 | "산업재해 예방을 위한 스마트 관제 플랫폼" | "로그인 관련 문의 | 000-0000-0000" + 하위 플랫폼 소개 문구 |

> **추가 수정 (SNB 위치 조정 및 아이콘 교체, 2026-04-17)**
>
> | 구분 | 파일 경로 | 변경 내용 |
> |------|-----------|-----------|
> | Frontend | `static/css/style.css` | `.snb-drawer` top `0` → `52px`, height `100vh` → `calc(100vh - 52px)` — 헤더 아래에서 열리도록 수정 |
> | Frontend | `static/css/style.css` | `.snb-overlay` `inset:0` → `top:52px` — 오버레이도 헤더 아래에만 적용 |
> | Frontend | `static/js/main_jh.js` | `iconMap` 이모지(🛡🖥⚙) → Material Design SVG 아이콘으로 교체 — OS·브라우저 무관하게 일관된 렌더링 |
>
> **변경 이유**
> - SNB가 `top:0`으로 헤더까지 덮어 햄버거 버튼이 가려지는 문제 → 헤더 높이(52px) 아래에서 열리도록 수정
> - 이모지 아이콘은 OS·브라우저마다 모양이 달라 디자인 불일치 → SVG 아이콘으로 통일

> **추가 수정 (홈 버튼 이동 경로 변경, 2026-04-17)**
>
> | 구분 | 파일 경로 | 변경 내용 |
> |------|-----------|-----------|
> | Frontend | `static/js/main_jh.js` | `handleHome()` 이동 경로 `/` → `/dashboard_jh/` 변경 |
>
> **변경 상세 (`main_jh.js` line 247, 250)**
> ```javascript
> // 변경 전
> if (window.location.pathname === '/') { ... }
> window.location.href = '/';
>
> // 변경 후
> if (window.location.pathname === '/dashboard_jh/') { ... }
> window.location.href = '/dashboard_jh/';
> ```
>
> | 현재 위치 | 클릭 결과 |
> |-----------|-----------|
> | `/dashboard_jh/` (메인) | 데이터 재조회 (새로고침 대체) |
> | 그 외 모든 페이지 | `/dashboard_jh/` 로 이동 |

> **추가 수정 (서브 페이지 URL 및 헤더 정상화, 2026-04-17)**
>
> | 구분 | 파일 경로 | 변경 내용 |
> |------|-----------|-----------|
> | Backend | `config/urls.py` | `dashboard_jh/safety/checklist/` URL 추가 — SNB 메뉴에서 해당 경로로 이동 시 404 발생하던 문제 해결 |
> | Frontend | `templates/safety_checklist.html` | 스크립트 `main.js` → `main_jh.js` 교체 — `main.js` 구문 오류로 인해 헤더 사용자 정보·시계가 렌더링되지 않던 문제 해결 |
>
> **변경 이유**
> - SNB 메뉴 path가 `/dashboard_jh/safety/checklist`로 설정되어 있어 해당 URL이 등록되지 않으면 404 반환
> - `main.js`는 `initWebSocket` 내부 구조 오류(line 545)로 JS 실행이 중단되어 `initApp()` 미동작 → 사용자 정보·시계 미표시
> - `main_jh.js`는 동일 기능을 오류 없이 제공하므로 서브 페이지에서도 동일하게 사용

---

## Backend 상세 변경 내역

### 1. `apps/accounts/models.py` — 수정

**변경 사항**
- `CustomUser.UserType`에 `superadmin('슈퍼관리자')` 항목 추가

```python
# 변경 전
class UserType(models.TextChoices):
    ADMIN  = 'admin',  '관리자'
    WORKER = 'worker', '작업자'

# 변경 후
class UserType(models.TextChoices):
    SUPERADMIN = 'superadmin', '슈퍼관리자'
    ADMIN      = 'admin',      '관리자'
    WORKER     = 'worker',     '작업자'
```

**이유**: 기능 정의서에서 `role: worker | admin | superadmin` 세 단계 권한을 요구

---

### 2. `apps/accounts/serializers.py` — 신규

**추가 클래스**
- `LoginSerializer` — 아이디/비밀번호를 받아 `authenticate()` 호출, 실패 시 한국어 오류 반환

---

### 3. `apps/accounts/views.py` — 신규

**추가 뷰**

| 클래스 | 메서드 | 엔드포인트 | 인증 |
|--------|--------|-----------|------|
| `LoginView` | POST | `/api/auth/login/` | 불필요 |
| `MeView` | GET | `/api/auth/me/` | JWT 필요 |
| `MenuView` | GET | `/api/menu/` | JWT 필요 |
| `DashboardRefreshView` | GET | `/api/dashboard/refresh/` | JWT 필요 |

**`LoginView` 응답 예시**
```json
{
  "access": "<JWT 액세스 토큰>",
  "refresh": "<JWT 리프레시 토큰>",
  "username": "작업자 A",
  "role": "worker"
}
```

**`MeView` 응답 예시**
```json
{
  "username": "작업자 A",
  "role": "worker",
  "menu_tree": [
    {
      "id": "safety",
      "label": "나의 안전확인",
      "icon": "shield",
      "children": [...]
    }
  ]
}
```

**`DashboardRefreshView` 응답 예시**
```json
{
  "last_updated": "2026-04-16T10:01:10",
  "admin_url": "/admin/"   // admin / superadmin 권한일 때만 포함
}
```

**권한별 메뉴 트리 규칙**

| role | 노출 메뉴 |
|------|-----------|
| `worker` | 나의 안전확인, 모니터링 |
| `admin` | 나의 안전확인, 모니터링, 관리자 전용 |
| `superadmin` | 나의 안전확인, 모니터링, 관리자 전용 |

---

### 4. `apps/accounts/urls.py` — 신규

```
/api/auth/login/          → LoginView
/api/auth/me/             → MeView
/api/auth/token/refresh/  → TokenRefreshView (SimpleJWT 기본 제공)
```

---

### 5. `config/settings.py` — 수정

**추가 설정**

```python
# REST Framework — JWT 인증 전역 적용
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# Simple JWT — 토큰 유효 기간
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# 백오피스 URL (환경변수로 재정의 가능)
ADMIN_BACKOFFICE_URL = env('ADMIN_BACKOFFICE_URL', default='/admin/')
```

**`.env`에 추가 가능한 항목**
```
ADMIN_BACKOFFICE_URL=https://admin.example.com
```

---

### 6. `config/urls.py` — 수정

**변경 전**: 대시보드 단일 뷰만 존재

**변경 후**: 로그인 페이지 + API 라우팅 전체 추가

```
GET  /               → dashboard.html 렌더링
GET  /login/         → login.html 렌더링
POST /api/auth/login/         → JWT 발급
GET  /api/auth/me/            → 사용자 정보 + 메뉴 트리
POST /api/auth/token/refresh/ → 토큰 갱신
GET  /api/menu/               → 메뉴 트리
GET  /api/dashboard/refresh/  → 대시보드 새로고침
GET  /admin/                  → Django 관리자
```

---

## Frontend 상세 변경 내역

### 7. `templates/login.html` — 신규

- 다크 테마 로그인 폼 (아이디 / 비밀번호)
- `POST /api/auth/login/` 호출 후 JWT 토큰을 `localStorage`에 저장
- 이미 로그인 상태(`access_token` 존재)면 `/`로 자동 이동
- 오류 메시지 인라인 표시

**localStorage 저장 키**
| 키 | 값 |
|----|-----|
| `access_token` | JWT 액세스 토큰 |
| `refresh_token` | JWT 리프레시 토큰 |
| `username` | 사용자명 |
| `role` | 사용자 권한 |

---

### 8. `templates/dashboard.html` — 수정

**추가된 마크업**

| 요소 | ID / 클래스 | 역할 |
|------|------------|------|
| SNB 오버레이 | `#snbOverlay` | SNB 열림 시 배경 어둡게 처리, 클릭 시 SNB 닫힘 |
| SNB Drawer | `#snbDrawer` | 좌측 슬라이드 메뉴 컨테이너 |
| SNB 닫기 버튼 | `#snbClose` | Drawer 내부 닫기 버튼 |
| SNB 메뉴 컨테이너 | `#snbMenu` | JS로 메뉴 트리 동적 렌더링 |
| SNB 오류 안내 | `#snbError` | 메뉴 로딩 실패 시 노출 |
| 헤더 사용자명 | `#headerUsername` | JS로 주입 |
| 헤더 권한 | `#headerRole` | JS로 주입 |
| 새로고침 버튼 | `#btnRefresh` | 데이터 재조회 |
| 홈 버튼 | `#btnHome` | 메인 이동 or 재조회 |
| 관리자 버튼 | `#btnAdmin` | 관리자 권한 시에만 노출, 백오피스 이동 |
| 로그아웃 버튼 | `#btnLogout` | 확인 모달 호출 |
| 로그아웃 모달 | `#logoutModal` | 로그아웃 확인 팝업 |

---

### 8-1. `templates/header.html` — 신규 (헤더 분리)

**변경 배경**
- `dashboard.html`에 인라인으로 작성된 헤더 마크업을 별도 파일로 분리
- 향후 다른 페이지에서도 동일한 헤더를 재사용할 수 있도록 `partials/` 폴더 구조 도입

**분리된 마크업 범위**

| 포함 요소 | 설명 |
|-----------|------|
| SNB 오버레이 (`#snbOverlay`) | SNB 열림 시 배경 처리 |
| SNB Drawer (`#snbDrawer`) | 좌측 슬라이드 메뉴 전체 |
| 헤더 (`<header class="header">`) | CM-01 / CM-02 전체 |
| 로그아웃 모달 (`#logoutModal`) | 로그아웃 확인 팝업 |

**`dashboard.html` 변경 전/후**

```html
<!-- 변경 전: 인라인 마크업 (~50줄) -->
<div id="snbOverlay" ...></div>
<nav id="snbDrawer" ...>...</nav>
<header class="header">...</header>
<div id="logoutModal" ...>...</div>

<!-- 변경 후: include 한 줄 -->
{% include 'header.html' %}
```

**재사용 방법**
다른 템플릿에서 헤더가 필요한 경우 동일하게 한 줄로 삽입:
```html
{% include 'header.html' %}
```

---

### 9. `static/css/style.css` — 수정

**추가된 스타일 블록**

| 스타일 | 설명 |
|--------|------|
| `.snb-overlay` | 반투명 배경, open 클래스로 노출 |
| `.snb-drawer` | 고정 좌측 패널, `translateX(-100%)` → `translateX(0)` 전환 |
| `.snb-depth1-btn` | Depth1 메뉴 버튼, hover 효과 |
| `.menu-arrow` | 펼침 화살표, `.expanded` 시 90° 회전 |
| `.snb-depth2` | 아코디언 하위 목록, `max-height` 전환으로 애니메이션 |
| `.snb-depth2 li a.active` | 현재 경로 파란 강조 + 좌측 테두리 |
| `.modal-backdrop` | 로그아웃 확인 팝업 배경 |
| `.modal-box` | 팝업 카드 |
| `@keyframes spin` | 새로고침 로딩 스피너 |

---

### 10. `static/js/main.js` — 수정

기존 차트/WebSocket 코드는 유지하고, 상단에 세 가지 모듈 추가:

**`Auth` 모듈**
- `getAccessToken()` / `getRole()` / `getUsername()` — localStorage 읽기
- `apiFetch(url, opts)` — `Authorization: Bearer <token>` 헤더 자동 주입
- `getMe()` — `/api/auth/me/` 호출, 401이면 로그인 페이지 리다이렉트
- `clear()` / `redirectLogin()` — 로그아웃 처리

**`SNB` 모듈 (CM-01)**
- `open()` / `close()` / `toggle()` — Drawer + Overlay 동시 제어
- `init()` — 햄버거, 닫기 버튼, 오버레이 클릭 이벤트 등록

**`Menu` 모듈 (SNB-01)**
- `render(menuTree)` — 서버 응답으로 Depth1/Depth2 DOM 동적 생성
- 현재 경로(`window.location.pathname`)와 일치하는 메뉴 `.active` 처리
- 현재 경로 포함 Depth1은 기본 펼침 상태
- Depth2 클릭 시 해당 경로 이동 + SNB 자동 닫힘
- 로드 실패 시 `#snbError` 노출

**`Header` 모듈 (CM-02)**
- `initClock()` — `setInterval(1000)`으로 현재 시간 갱신, `YYYY.MM.DD HH:MM:SS` 포맷
- `updateLastUpdated()` — 새로고침 완료 후 `최종 갱신: HH:MM:SS` 갱신
- `handleRefresh()` — `/api/dashboard/refresh/` 호출, 중복 요청 방지(`isRefreshing` 플래그), 로딩 스피너
- `handleHome()` — 현재 경로가 `/`이면 `handleRefresh()`, 아니면 페이지 이동
- `handleAdmin()` — 서버에서 받은 `admin_url`로 이동
- `renderUser(username, role)` — 헤더 사용자명/권한 표시
- `showAdminBtn(role)` — `admin` / `superadmin`일 때만 관리자 버튼 노출
- `initLogout()` — 로그아웃 모달 표시, 확인 시 `Auth.redirectLogin()` 호출

**`initApp()` 진입점**
```
1. localStorage에 access_token 없으면 → /login/ 리다이렉트
2. GET /api/auth/me/ 호출
3. 성공: 헤더 사용자 정보 렌더링 + SNB 메뉴 렌더링
4. 실패: cached 값으로 헤더 표시, SNB 오류 안내
5. SNB.init() / Header.init() / initCharts() / initWebSocket() 호출
```

---

## 마이그레이션

```bash
# 아래 두 마이그레이션이 자동 생성 및 적용됨
apps/accounts/migrations/0004_alter_customuser_user_type.py
```

실행 명령:
```bash
python manage.py makemigrations
python manage.py migrate
```

---

## 동작 흐름 요약

```
[브라우저 접속 /]
      ↓
[main.js] access_token 확인
      ├─ 없음 → /login/ 리다이렉트
      └─ 있음 → GET /api/auth/me/
                    ├─ 401 → /login/ 리다이렉트
                    └─ 200 → 헤더 사용자명/권한 렌더링
                              SNB 메뉴 트리 렌더링
                              시계 시작 (1초 갱신)
                              WebSocket 연결

[햄버거 클릭] → SNB Drawer 슬라이드 인
[Depth1 클릭] → 아코디언 Depth2 펼침
[Depth2 클릭] → 해당 경로 이동 + SNB 닫힘
[새로고침 클릭] → GET /api/dashboard/refresh/ → 최종 갱신 시간 업데이트
[홈 클릭] → 메인이면 새로고침, 아니면 / 이동
[관리자 버튼] → admin_url로 이동 (admin/superadmin만 노출)
[로그아웃] → 확인 팝업 → localStorage 초기화 → /login/ 이동
```

---

## 완료 기준 체크

### CM-01
- [x] 로그인 후 모든 화면에서 헤더가 고정 노출된다
- [x] 헤더에 로고, 시스템명, 사용자명이 표시된다
- [x] 햄버거 버튼 클릭 시 SNB가 열린다
- [x] 햄버거 버튼 재클릭 시 SNB가 닫힌다
- [x] 권한에 따라 메뉴가 다르게 노출된다
- [x] 사용자 정보 조회 실패 시 `-` 처리된다

### CM-02
- [x] 현재 시스템 시간이 헤더에 표시되고 1초마다 갱신된다
- [x] 마지막 갱신 시간이 새로고침 후 업데이트된다
- [x] 새로고침 클릭 시 현재 화면 데이터가 재호출된다
- [x] 새로고침 중 로딩 스피너가 표시된다
- [x] 홈 아이콘 클릭 시 메인 대시보드로 이동한다
- [x] 메인 화면에서 홈 클릭 시 데이터 재호출로 대체된다
- [x] 관리자 메뉴 버튼은 관리자 권한 이상에서만 노출된다
- [x] 관리자 메뉴 클릭 시 백오피스 URL로 이동한다

### SNB-01
- [x] 햄버거 클릭 시 SNB가 좌측에서 슬라이드 인된다
- [x] Depth1 메뉴에 아이콘과 메뉴명이 표시된다
- [x] Depth1 클릭 시 Depth2 하위 메뉴가 아코디언으로 펼쳐진다
- [x] Depth2 메뉴 클릭 시 해당 화면으로 이동한다
- [x] 현재 활성 메뉴가 하이라이트 처리된다
- [x] 권한 없는 메뉴는 노출되지 않는다
- [x] 메뉴 overflow 시 스크롤이 동작한다
- [x] 메뉴 트리 조회 실패 시 오류 안내가 표시된다

---

## 스크린샷 검토 반영 (2026-04-16)

화면 설계서 스크린샷의 헤더 영역(① ~ ⑦)과 코드를 비교하여 누락된 요소를 수정하였습니다.

### 헤더 ① ~ ⑦ 항목 정의

| 번호 | 요소 | 위치 |
|------|------|------|
| ① | 햄버거 버튼 (☰) | 헤더 좌측 |
| ② | 로고 박스 | 헤더 좌측 |
| ③ | 시스템명 텍스트 | 헤더 좌측 |
| ④ | 사용자명(`홍 길 동님`) / `환영합니다.` + **관리자 메뉴 버튼** | 헤더 가운데 |
| ⑤ | 현재 시간 + 최종 갱신 시간 | 헤더 우측 |
| ⑥ | 아이콘 버튼 그룹 (⟳ · 🏠 SVG) | 헤더 우측 |
| ⑦ | 로그아웃 버튼 | 헤더 우측 끝 |

### 스크린샷과 코드 비교

| 항목 | 스크린샷 | 기존 코드 | 조치 |
|------|----------|-----------|------|
| ⑥ 아이콘 — 알림 벨 (🔔) | 있음 (배지 포함) | **없음** (구현 누락) | 추가 후 → **UI 피드백으로 제거** |
| ⑥ 아이콘 — 홈 버튼 크기 | 크게 표시 | SVG 17px | **22px으로 확대** |
| ⑥ 아이콘 순서 (최종) | ⟳ → 🏠 | ⟳ → 🏠 | 일치 |
| ④ 관리자 메뉴 버튼 | "관리자 메뉴 →" 텍스트 버튼, 사용자 정보 옆 위치 | ⚙ 아이콘 (위치·형태 불일치) | **텍스트 버튼으로 교체, header-center로 이동** |

### 수정 상세

**`templates/header.html`**
```html
<!-- 변경 전 -->
<button id="btnRefresh" ...>⟳</button>
<button id="btnHome"    ...>🏠</button>
<button id="btnAdmin"   ... style="display:none;">⚙</button>

<!-- 변경 후 — 🔔 알림 버튼 추가 -->
<button id="btnRefresh" ...>⟳</button>
<button id="btnHome"    ...>🏠</button>
<button id="btnAdmin"   ... style="display:none;">⚙</button>
<button id="btnAlarm"   ...>🔔<span id="alarmBadge" class="badge">0</span></button>
```

**`static/js/main.js`**
- `Header.updateAlarmBadge(count)` 메서드 추가
  - 배지 숫자를 동적으로 갱신, `count === 0`이면 배지 숨김, `count > 99`이면 `99+` 표시
- WebSocket 메시지에서 `data.alarm_count` 수신 시 배지 자동 업데이트

---

## 스크린샷 검토 2차 반영 (2026-04-16)

### ③ 사용자 표시 형식 변경

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 첫째 줄 | `admin` (username 그대로) | `admin님` (username + 님) |
| 둘째 줄 | `관리자` (role 한글 변환) | `환영합니다.` (고정 문구) |

**`static/js/main.js` — `Header.renderUser()`**
```javascript
// 변경 전
renderUser(username, role) {
  const roleLabel = { worker: '작업자', admin: '관리자', superadmin: '슈퍼관리자' };
  nameEl.textContent = username || '-';
  roleEl.textContent = roleLabel[role] || role || '-';
}

// 변경 후
renderUser(username) {
  nameEl.textContent = username ? `${username}님` : '-';
  roleEl.textContent = '환영합니다.';
}
```

---

### ⑥ 홈 버튼 아이콘 변경

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 아이콘 | 🏠 (이모지) | SVG 하우스 아이콘 (Material Design) |
| 이유 | 이모지는 OS·브라우저마다 렌더링 차이 발생 | SVG는 색상·크기 일관 적용, 스크린샷 디자인에 부합 |

**`templates/header.html`**
```html
<!-- 변경 전 -->
<button id="btnHome" ...>🏠</button>

<!-- 변경 후 -->
<button id="btnHome" ...>
  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
    <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>
  </svg>
</button>
```

**홈 버튼 동작**

| 현재 위치 | 클릭 결과 |
|-----------|-----------|
| `/` (메인 대시보드) | 데이터 재조회 (새로고침 대체) |
| 그 외 모든 페이지 | `/` 로 이동 → 메인 대시보드 복귀 |

---

### 작업 전 안전 확인 임시 페이지 추가 (SNB-02 검증용)

홈 버튼의 페이지 복귀 동작을 검증하기 위해 서브 페이지를 임시 생성하였습니다.

**신규 파일**: `templates/safety_checklist.html`
- 헤더(`{% include 'header.html' %}`) 포함 — 홈 버튼, SNB 동일하게 동작
- 브레드크럼 `나의 안전확인 > 작업 전 안전 확인` 표시
- 체크리스트 테이블 (더미 데이터)

**URL**: `GET /safety/checklist/` → `config/urls.py`에 추가

**검증 시나리오**
```
1. SNB 열기 → 나의 안전확인 > 작업 전 안전 확인 클릭
2. /safety/checklist/ 페이지 진입 확인
3. 헤더 홈 버튼(🏠 SVG) 클릭
4. / (메인 대시보드) 로 복귀 확인
```

---

## 로그인 화면 추가 수정 (2026-04-17)

### 로그인 후 이동 경로 수정

| 구분 | 파일 경로 | 변경 내용 |
|------|-----------|-----------|
| Frontend | `templates/login.html` | 로그인 성공 및 기존 토큰 감지 시 이동 경로 `/` → `/dashboard_jh/` 변경 |

**변경 이유**
- `/` 경로는 `dashboard_sh.html`을 서빙하며, 해당 파일은 `main.js`를 사용
- `main.js`는 line 545 구문 오류로 `initApp()` 미실행 → 로그아웃 버튼 이벤트 미등록 → 클릭해도 아무 반응 없음
- `/dashboard_jh/`는 `main_jh.js`를 사용하므로 `initLogout()` 정상 등록

**변경 상세 (`login.html`)**
```javascript
// 변경 전
window.location.href = '/';   // 이미 로그인 상태 체크 + 로그인 성공 후

// 변경 후
window.location.href = '/dashboard_jh/';
```

---

### ② X 클리어 버튼 추가

| 구분 | 파일 경로 | 변경 내용 |
|------|-----------|-----------|
| Frontend | `templates/login.html` | 아이디·비밀번호 입력란에 X 클리어 버튼 추가 |

**변경 상세**

| 항목 | 내용 |
|------|------|
| CSS | `.input-wrap` (relative 컨테이너), `.clear-btn` (기본 `display:none`, `.visible` 시 표시) |
| HTML | 각 `<input>`을 `<div class="input-wrap">`으로 감싸고 `<button class="clear-btn">` 추가 |
| JS | 텍스트 입력 시 `syncClear()` 호출 → X 버튼 자동 표시, 클릭 시 입력값 삭제·버튼 숨김·포커스 복귀 |

**동작**
```
텍스트 입력 → X 버튼 노출
X 버튼 클릭 → 입력값 삭제 + X 버튼 숨김 + 해당 필드 포커스 복귀
```

---

### 필드별 유효성 검사 및 인라인 에러 메시지 추가

| 구분 | 파일 경로 | 변경 내용 |
|------|-----------|-----------|
| Frontend | `templates/login.html` | 아이디·비밀번호 필드별 유효성 검사 및 인라인 에러 메시지 추가 |

**에러 케이스**

| 필드 | 조건 | 메시지 |
|------|------|--------|
| 아이디 | 미입력 | 아이디를 입력해주세요. |
| 아이디 | 영문/숫자 외 문자 포함 | 아이디는 영문 또는 숫자만 입력할 수 있습니다. |
| 아이디 | 4자 미만 또는 20자 초과 | 아이디를 4~20자로 입력해주세요. |
| 비밀번호 | 미입력 | 비밀번호를 입력해주세요. |
| 비밀번호 | 8자 미만 | 비밀번호를 8자 이상 입력해야 합니다. |
| 비밀번호 | 영문·숫자·특수문자 중 2종류 미만 | 비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다. |

**변경 상세**

| 항목 | 내용 |
|------|------|
| CSS | `.field-error` (기본 숨김, `.show` 시 빨간 텍스트 표시), `input.error` (빨간 테두리+그림자) |
| HTML | 각 `.input-wrap` 아래 `<div class="field-error" id="usernameError/passwordError">` 추가 |
| JS | `validateUsername()` / `validatePassword()` 함수 추가, 폼 제출 시 검사 후 실패 시 `showFieldError()` 호출 |

**동작 흐름**
```
[로그인 버튼 클릭]
  → 클라이언트 유효성 검사
  → 실패: 해당 필드 아래 빨간 에러 메시지 표시 + 입력창 빨간 테두리
  → 성공: API 호출

[입력 중 / X 버튼 클릭]
  → 에러 메시지 자동 제거 + 빨간 테두리 제거
```

---

## 서버측 유효성 검사 추가 (2026-04-20)

### 배경

`login.html` 229번 줄에 클라이언트 유효성 검사 로직이 존재하지만, `LoginSerializer`와 `LoginView`에 동일한 서버측 검사가 없어 API를 직접 호출하면 규칙이 무시되는 문제가 있었습니다.

### 변경 파일

| 구분 | 파일 경로 | 변경 내용 |
|------|-----------|-----------|
| Backend | `apps/accounts/serializers.py` | `validate_username()` / `validate_password()` 추가 |
| Backend | `apps/accounts/views.py` | 필드별 에러 응답 및 HTTP 상태코드 분리 |

---

### `apps/accounts/serializers.py` — 수정

**추가된 유효성 검사 규칙**

| 필드 | 조건 | 메시지 |
|------|------|--------|
| 아이디 | 영문/숫자 외 문자 포함 | 아이디는 영문 또는 숫자만 입력할 수 있습니다. |
| 아이디 | 4자 미만 또는 20자 초과 | 아이디를 4~20자로 입력해주세요. |
| 비밀번호 | 8자 미만 | 비밀번호를 8자 이상 입력해야 합니다. |
| 비밀번호 | 영문·숫자·특수문자 중 2종류 미만 | 비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다. |

**변경 상세**

```python
# 추가 전 — 필드 검사 없음, authenticate() 결과만 확인
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(...)
        if not user:
            raise serializers.ValidationError("아이디 또는 비밀번호가 올바르지 않습니다.")
        ...

# 추가 후 — 필드별 validate_* 메서드 추가
def validate_username(self, value):
    if not re.fullmatch(r"[a-zA-Z0-9]+", value):
        raise serializers.ValidationError("아이디는 영문 또는 숫자만 입력할 수 있습니다.")
    if not (4 <= len(value) <= 20):
        raise serializers.ValidationError("아이디를 4~20자로 입력해주세요.")
    return value

def validate_password(self, value):
    if len(value) < 8:
        raise serializers.ValidationError("비밀번호를 8자 이상 입력해야 합니다.")
    types = sum(
        bool(pattern.search(value))
        for pattern in [re.compile(r"[a-zA-Z]"), re.compile(r"[0-9]"), re.compile(r"[^a-zA-Z0-9]")]
    )
    if types < 2:
        raise serializers.ValidationError("비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다.")
    return value
```

---

### `apps/accounts/views.py` — 수정

**변경 상세**

```python
# 변경 전 — non_field_errors만 확인, 모든 오류에 401 반환
if not serializer.is_valid():
    errors = serializer.errors.get("non_field_errors", ["입력값을 확인해주세요."])
    return Response({"error": errors[0]}, status=status.HTTP_401_UNAUTHORIZED)

# 변경 후 — 필드별 오류와 인증 오류를 상태코드로 구분
if not serializer.is_valid():
    for field in ("username", "password", "non_field_errors"):
        if field in serializer.errors:
            return Response(
                {"error": serializer.errors[field][0]},
                status=status.HTTP_400_BAD_REQUEST
                if field in ("username", "password")
                else status.HTTP_401_UNAUTHORIZED,
            )
    return Response({"error": "입력값을 확인해주세요."}, status=status.HTTP_400_BAD_REQUEST)
```

**HTTP 상태코드 응답 규칙**

| 오류 종류 | 상태코드 | 예시 |
|-----------|----------|------|
| 아이디/비밀번호 형식 오류 | `400 Bad Request` | 아이디를 4~20자로 입력해주세요. |
| 인증 실패 (아이디·비밀번호 불일치) | `401 Unauthorized` | 아이디 또는 비밀번호가 올바르지 않습니다. |

---

### 동작 흐름 (서버측 추가 후)

```
[POST /api/auth/login/]
  → validate_username() — 형식/길이 검사 → 실패 시 400 반환
  → validate_password() — 길이/복잡도 검사 → 실패 시 400 반환
  → validate()          — authenticate() 인증 → 실패 시 401 반환
  → 성공: JWT 토큰 발급
```

---

## 최종 갱신 시간 날짜 표시 추가 (2026-04-20)

### 배경

헤더의 현재 시스템 시간은 `YYYY.MM.DD HH:MM:SS` 형식으로 표시되는 반면,
최종 갱신 시간은 `HH:MM:SS`만 표시되어 형식이 불일치하였습니다.

### 변경 파일

| 구분 | 파일 경로 | 변경 내용 |
|------|-----------|-----------|
| Frontend | `static/js/refactors/util.js` | `nowDateLabel()` 신규 추가 |
| Frontend | `static/js/refactors/layout.js` | `updateLastUpdated()`에서 `nowDateLabel()` 사용 |

### 변경 상세

**`static/js/refactors/util.js`**

```javascript
// 기존 유지 — 차트 X축 라벨용 (HH:MM:SS)
function nowLabel() {
  const d = new Date();
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// 신규 추가 — 최종 갱신 표시용 (YYYY.MM.DD HH:MM:SS)
function nowDateLabel() {
  const d = new Date();
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
```

> `nowLabel()`을 수정하면 `websocket.js`의 차트 X축 라벨이 날짜까지 표시되어 깨지는 문제가 발생하므로
> 함수를 분리하여 용도별로 사용합니다.

**`static/js/refactors/layout.js` — `updateLastUpdated()` 수정**

```javascript
// 변경 전
el.textContent = nowLabel();

// 변경 후
el.textContent = nowDateLabel();
```

**표시 결과 비교**

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 현재 시스템 시간 | `2026.04.20 16:01:36` | `2026.04.20 16:01:36` (유지) |
| 최종 갱신 | `16:01:13` | `2026.04.20 16:01:13` |
| 차트 X축 라벨 | `16:01:13` | `16:01:13` (유지) |

---

## 코드 품질 개선 (2026-04-20)

### 배경

코드 리뷰를 통해 발견된 중복 코드, 가독성 문제, 전역 오염 가능성을 개선하였습니다.

### 변경 파일

| 구분 | 파일 경로 | 변경 내용 |
|------|-----------|-----------|
| Backend | `apps/accounts/serializers.py` | 정규식 패턴 모듈 상수로 분리 |
| Backend | `apps/accounts/views.py` | 에러 처리 로직 가독성 개선 |
| Frontend | `static/css/login.css` | `body` → `body.login-page` 스코프 제한 |
| Frontend | `templates/auth/login.html` | `<body class="login-page">` 추가 |

---

### 1. `apps/accounts/serializers.py` — `re.compile` 중복 생성 제거

`validate_password()`가 호출될 때마다 정규식 패턴 3개를 매번 새로 컴파일하던 문제를 모듈 상단 상수로 분리하여 해결하였습니다.

```python
# 변경 전 — 호출마다 컴파일
types = sum(
    bool(pattern.search(value))
    for pattern in [re.compile(r"[a-zA-Z]"), re.compile(r"[0-9]"), re.compile(r"[^a-zA-Z0-9]")]
)

# 변경 후 — 모듈 로드 시 1회만 컴파일
_PWD_PATTERNS = [re.compile(r"[a-zA-Z]"), re.compile(r"[0-9]"), re.compile(r"[^a-zA-Z0-9]")]

types = sum(bool(p.search(value)) for p in _PWD_PATTERNS)
```

---

### 2. `apps/accounts/views.py` — 에러 처리 로직 가독성 개선

`for` + 삼항연산자 조합을 필드 오류 / 인증 오류로 명시적으로 분리하였습니다.

```python
# 변경 전 — for loop + 삼항연산자 조합
for field in ("username", "password", "non_field_errors"):
    if field in serializer.errors:
        return Response(
            {"error": serializer.errors[field][0]},
            status=status.HTTP_400_BAD_REQUEST
            if field in ("username", "password")
            else status.HTTP_401_UNAUTHORIZED,
        )

# 변경 후 — 상태코드별 명시적 분리
errors = serializer.errors
for field in ("username", "password"):
    if field in errors:
        return Response({"error": errors[field][0]}, status=status.HTTP_400_BAD_REQUEST)
if "non_field_errors" in errors:
    return Response({"error": errors["non_field_errors"][0]}, status=status.HTTP_401_UNAUTHORIZED)
return Response({"error": "입력값을 확인해주세요."}, status=status.HTTP_400_BAD_REQUEST)
```

---

### 3. `login.css` / `login.html` — body 전역 오염 방지

`login.css`의 `body` 스타일이 다른 페이지에서 실수로 import될 경우 레이아웃을 깨뜨릴 수 있어 클래스 스코프로 제한하였습니다.

```css
/* 변경 전 */
body { display:flex; align-items:center; justify-content:center; }

/* 변경 후 */
body.login-page { display:flex; align-items:center; justify-content:center; }
```

```html
<!-- login.html body 태그 -->
<!-- 변경 전 -->
<body>

<!-- 변경 후 -->
<body class="login-page">
```
