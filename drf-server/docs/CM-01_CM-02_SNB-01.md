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
