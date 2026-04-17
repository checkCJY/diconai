# 리팩토링 보고서 v6 — URL 구조 개편 / dashboard 앱 신규 생성

> 작성일: 2026-04-17
> 브랜치: `feature/snb_header.v1`
> 기준 문서: `docs/refactoring_report_v5.md` (파일 정리 / 기능 통합 / 템플릿 구조화)

---

## 1. 요약 (Summary)

v5 이후 `config/urls.py`가 뷰 함수 정의 + 라우팅을 동시에 담당하고 있었고,
`accounts/views.py`에 인증과 무관한 대시보드 뷰(`MenuView`, `DashboardRefreshView`, 메뉴 트리 데이터)가 섞여 있었습니다.

이번 v6 작업에서는 **`apps/dashboard/` 앱을 신규 생성**하고, `config/urls.py`를 **순수 라우터**로 교체했습니다.

---

## 2. 변경 사유 (Key Reasons)

### 사유 1 — 단일 책임 원칙
`accounts` 앱은 인증(로그인·토큰·사용자 정보)만 담당해야 합니다.
메뉴 트리, 대시보드 갱신은 대시보드 도메인이므로 별도 앱으로 분리합니다.

### 사유 2 — config/urls.py 역할 명확화
뷰 함수를 직접 정의하는 것은 각 앱의 책임입니다.
`config/urls.py`는 어느 URL 그룹을 어느 앱이 처리하는지만 선언합니다.

### 사유 3 — 확장성
이후 대시보드 관련 모델, 시리얼라이저, 권한 등이 추가될 때 `apps/dashboard/` 안에서 관리할 수 있습니다.

---

## 3. 신규 생성 파일 — apps/dashboard/

```
apps/dashboard/
├── __init__.py
├── apps.py          ← DashboardConfig
├── menu.py          ← 메뉴 트리 데이터 + get_menu_tree()
├── views.py         ← HTML 뷰 2개 + MenuView + DashboardRefreshView
└── urls.py          ← HTML 페이지 3개 + API 2개
```

### menu.py

`accounts/views.py`에 있던 메뉴 트리 정의를 독립 모듈로 분리했습니다.

| 항목 | 내용 |
|------|------|
| `_MENU_WORKER` | 작업자 공통 메뉴 트리 (나의 안전확인, 모니터링) |
| `_MENU_ADMIN_EXTRA` | 관리자 전용 추가 메뉴 |
| `get_menu_tree(role)` | role 기반 메뉴 트리 반환 |

> `accounts/views.py`의 `MeView`와 `dashboard/views.py`의 `MenuView` 모두 이 모듈을 import합니다.

### views.py

| 뷰 | 종류 | URL | 이동 전 위치 |
|----|------|-----|-------------|
| `main_dashboard` | HTML | `/` , `/dashboard/` | `config/urls.py` |
| `safety_checklist_page` | HTML | `/safety/checklist/` | `config/urls.py` |
| `MenuView` | API (GET) | `/api/menu/` | `accounts/views.py` |
| `DashboardRefreshView` | API (GET) | `/api/dashboard/refresh/` | `accounts/views.py` |

### urls.py

```python
urlpatterns = [
    # HTML 페이지
    path("",                   views.main_dashboard,        name="main-dashboard"),
    path("dashboard/",         views.main_dashboard,        name="main-dashboard-alt"),
    path("safety/checklist/",  views.safety_checklist_page, name="safety-checklist"),
    # API
    path("api/menu/",              views.MenuView.as_view(),           name="api-menu"),
    path("api/dashboard/refresh/", views.DashboardRefreshView.as_view(), name="api-dashboard-refresh"),
]
```

---

## 4. 수정된 파일

### accounts/views.py

| 변경 내용 | 상세 |
|-----------|------|
| 제거 | `_MENU_WORKER`, `_MENU_ADMIN_EXTRA`, `get_menu_tree()` |
| 제거 | `MenuView`, `DashboardRefreshView` |
| 제거 | `from datetime import datetime`, `from django.conf import settings` |
| 추가 | `from apps.dashboard.menu import get_menu_tree` |

`MeView`는 `menu_tree`를 반환해야 하므로 `accounts`에 유지하되, 메뉴 데이터는 `dashboard.menu`에서 import합니다.

### accounts/urls.py

accounts 앱이 자신의 모든 URL(HTML + API)을 직접 관리하도록 변경했습니다.

```python
# Before — config/urls.py에서 login 페이지 직접 정의 후 include
path("login/", login_page),
path("api/auth/", include("apps.accounts.urls")),  # 내부 경로: login/, me/, token/refresh/

# After — accounts/urls.py가 전체 경로 자체 관리
path("login/",                  login_page,                  name="login"),
path("api/auth/login/",         views.LoginView.as_view(),   name="api-login"),
path("api/auth/me/",            views.MeView.as_view(),      name="api-me"),
path("api/auth/token/refresh/", TokenRefreshView.as_view(),  name="token-refresh"),
```

> **주의:** 기존 `api/auth/` prefix include 방식에서 전체 경로 직접 선언 방식으로 변경됩니다.
> 프론트엔드 `auth.js`의 API 엔드포인트 경로는 동일(`/api/auth/login/`, `/api/auth/me/`)하므로 변경 없음.

### config/urls.py

```python
# Before
from apps.accounts.views import DashboardRefreshView, MenuView

def login_page(request): ...
def main_dashboard(request): ...
def safety_checklist_page(request): ...

urlpatterns = [
    path("admin/", ...),
    path("", main_dashboard),
    path("dashboard/", main_dashboard),
    path("login/", login_page),
    path("safety/checklist/", safety_checklist_page),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/alarms/", include("apps.alarms.urls")),
    path("api/menu/", MenuView.as_view()),
    path("api/dashboard/refresh/", DashboardRefreshView.as_view()),
]

# After — 순수 라우터
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.dashboard.urls")),
    path("api/alarms/", include("apps.alarms.urls")),
]
```

### config/settings.py

```python
INSTALLED_APPS = [
    ...
    "apps.accounts",
    "apps.dashboard",   # 추가
    "apps.alarms",
    ...
]
```

---

## 5. 전체 URL 매핑표 (After)

| URL | 앱 | 뷰 | 종류 |
|-----|----|----|------|
| `admin/` | Django | AdminSite | 관리자 |
| `login/` | accounts | `login_page` | HTML |
| `api/auth/login/` | accounts | `LoginView` | API |
| `api/auth/me/` | accounts | `MeView` | API |
| `api/auth/token/refresh/` | accounts | `TokenRefreshView` | API |
| `/` | dashboard | `main_dashboard` | HTML |
| `dashboard/` | dashboard | `main_dashboard` | HTML |
| `safety/checklist/` | dashboard | `safety_checklist_page` | HTML |
| `api/menu/` | dashboard | `MenuView` | API |
| `api/dashboard/refresh/` | dashboard | `DashboardRefreshView` | API |
| `api/alarms/` | alarms | `AlarmRecordViewSet` 외 | API |

---

## 6. 앱별 책임 요약

| 앱 | 책임 |
|----|------|
| `accounts` | 로그인 페이지 렌더, JWT 인증, 사용자 정보 조회 |
| `dashboard` | 대시보드·체크리스트 페이지 렌더, 메뉴 트리, 대시보드 갱신 API |
| `alarms` | 알람 기록 CRUD, 작업자 상태, 24시간 요약 |
| `geofence` | 지오펜스 데이터 |
| `sensors` | 센서 데이터 |

---

## 7. 변경사항 비교 (Before / After)

| 구분 | v5 | v6 |
|------|----|----|
| config/urls.py 뷰 정의 수 | 3개 | **0개** (순수 라우터) |
| config/urls.py import 수 | 3개 (`DashboardRefreshView`, `MenuView`, `render`) | **2개** (`admin`, `include`, `path`) |
| accounts/views.py 뷰 수 | 4개 (인증 2 + 대시보드 2) | **2개** (인증만) |
| 앱 수 | 4개 | **5개** (`dashboard` 추가) |
| 메뉴 트리 위치 | `accounts/views.py` 내 하드코딩 | `dashboard/menu.py` 독립 모듈 |
