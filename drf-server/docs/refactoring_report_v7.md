# 리팩토링 보고서 v7 — URL 앱 접두사 구조 / 전체 엔드포인트 경로 변경

> 작성일: 2026-04-17
> 브랜치: `feature/snb_header.v1`
> 기준 문서: `docs/refactoring_report_v6.md` (dashboard 앱 신규 생성 / config 순수 라우터화)

---

## 1. 요약 (Summary)

v6에서 `config/urls.py`를 순수 라우터로 교체했지만, 앱별 URL이 동일한 루트에 평탄하게 나열되어 있어 어느 앱이 어떤 경로를 담당하는지 명확하지 않았습니다.

이번 v7 작업에서는 **앱 이름을 URL 접두사로 사용**하여 경로만 봐도 담당 앱을 알 수 있게 했습니다.
이에 따라 프론트엔드 JS 파일의 모든 하드코딩 API 경로도 일괄 수정했습니다.

---

## 2. 변경 사유 (Key Reasons)

### 사유 1 — URL만으로 담당 앱 식별
`/api/alarms/` 와 `/api/dashboard/refresh/` 는 접두사만 봐서는 어느 앱이 처리하는지 알기 어렵습니다.
`/alarms/api/` · `/dashboard/api/refresh/` 처럼 **앱 이름이 접두사**가 되면 라우팅 흐름이 직관적으로 드러납니다.

### 사유 2 — 앱 독립성 강화
각 앱이 자신의 URL 네임스페이스 안에서 내부 경로를 완전히 자율 관리합니다.
`config/urls.py`는 어느 앱이 어느 접두사를 담당하는지만 선언합니다.

---

## 3. URL 전체 경로 변경표

### 3-1. 페이지 URL

| 설명 | 변경 전 | 변경 후 |
|------|---------|---------|
| 루트 접속 | `/` (대시보드 직접 렌더) | `/` → **302 redirect** → `/dashboard/` |
| 메인 대시보드 | `/` 또는 `/dashboard/` | `/dashboard/` |
| 로그인 페이지 | `/login/` | `/accounts/login/` |
| 안전확인 체크리스트 | `/safety/checklist/` | `/dashboard/safety/checklist/` |

### 3-2. API 엔드포인트

| 설명 | 변경 전 | 변경 후 |
|------|---------|---------|
| 로그인 | `/api/auth/login/` | `/accounts/api/auth/login/` |
| 내 정보 조회 | `/api/auth/me/` | `/accounts/api/auth/me/` |
| 토큰 갱신 | `/api/auth/token/refresh/` | `/accounts/api/auth/token/refresh/` |
| 메뉴 트리 | `/api/menu/` | `/dashboard/api/menu/` |
| 대시보드 갱신 | `/api/dashboard/refresh/` | `/dashboard/api/refresh/` |
| 알람 목록 (CRUD) | `/api/alarms/` | `/alarms/api/` |
| 알람 요약 | `/api/alarms/summary/` | `/alarms/api/summary/` |
| 내 작업자 상태 | `/api/alarms/my-status/` | `/alarms/api/my-status/` |
| 작업자 전체 현황 | `/api/alarms/worker-summary/` | `/alarms/api/worker-summary/` |

---

## 4. 서버 코드 변경 내역

### config/urls.py

```python
# Before
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.dashboard.urls")),
    path("api/alarms/", include("apps.alarms.urls")),
]

# After
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("accounts/", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("alarms/",    include("apps.alarms.urls")),
]
```

### dashboard/urls.py

```python
# 변경점
# - path("dashboard/", ...) 제거 → /dashboard/dashboard/ 방지
# - api/dashboard/refresh/ → api/refresh/ 단축
urlpatterns = [
    path("",                   views.main_dashboard,         name="main-dashboard"),
    path("safety/checklist/",  views.safety_checklist_page,  name="safety-checklist"),
    path("api/menu/",          views.MenuView.as_view(),     name="api-menu"),
    path("api/refresh/",       views.DashboardRefreshView.as_view(), name="api-dashboard-refresh"),
]
```

### alarms/urls.py

```python
# Before
router.register(r"alarms", AlarmRecordViewSet, basename="alarm")
urlpatterns = [
    path("", include(router.urls)),        # /api/alarms/alarms/
    path("my-status/", ...),               # /api/alarms/my-status/
    path("worker-summary/", ...),          # /api/alarms/worker-summary/
]

# After
router.register(r"", AlarmRecordViewSet, basename="alarm")
urlpatterns = [
    path("api/", include(router.urls)),        # /alarms/api/
    path("api/my-status/", ...),               # /alarms/api/my-status/
    path("api/worker-summary/", ...),          # /alarms/api/worker-summary/
]
```

---

## 5. 프론트엔드 JS 변경 내역

### auth.js

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| `getMe()` URL | `/api/auth/me/` | `/accounts/api/auth/me/` |
| `redirectLogin()` | `/login/` | `/accounts/login/` |

### layout.js

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| `handleRefresh()` URL | `/api/dashboard/refresh/` | `/dashboard/api/refresh/` |
| `handleHome()` 경로 비교 | `pathname === '/'` | `pathname === '/dashboard/'` |
| `handleHome()` 이동 URL | `/` | `/dashboard/` |

### event-panel.js

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 이벤트 목록 | `/api/alarms/?ordering=...` | `/alarms/api/?ordering=...` |
| 24시간 요약 | `/api/alarms/summary/` | `/alarms/api/summary/` |

### worker-panel.js

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| `API_MY_STATUS` | `/api/alarms/my-status/` | `/alarms/api/my-status/` |
| `API_WORKER_SUMMARY` | `/api/alarms/worker-summary/` | `/alarms/api/worker-summary/` |

### main_dashboard.html

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 안전확인 버튼 링크 | `/safety/checklist/` | `/dashboard/safety/checklist/` |

---

## 6. 최종 URL 매핑표

| URL | 앱 | 뷰 / 역할 | 종류 |
|-----|----|-----------|----|
| `admin/` | Django | AdminSite | 관리자 |
| `/` | config | RedirectView → `/dashboard/` | redirect |
| `accounts/login/` | accounts | `login_page` | HTML |
| `accounts/api/auth/login/` | accounts | `LoginView` | API |
| `accounts/api/auth/me/` | accounts | `MeView` | API |
| `accounts/api/auth/token/refresh/` | accounts | `TokenRefreshView` | API |
| `dashboard/` | dashboard | `main_dashboard` | HTML |
| `dashboard/safety/checklist/` | dashboard | `safety_checklist_page` | HTML |
| `dashboard/api/menu/` | dashboard | `MenuView` | API |
| `dashboard/api/refresh/` | dashboard | `DashboardRefreshView` | API |
| `alarms/api/` | alarms | `AlarmRecordViewSet` (CRUD) | API |
| `alarms/api/summary/` | alarms | `AlarmRecordViewSet` (@action) | API |
| `alarms/api/my-status/` | alarms | `MyStatusView` | API |
| `alarms/api/worker-summary/` | alarms | `WorkerSummaryView` | API |

---

## 7. 테스트 체크리스트

### 서버 실행

```bash
# Django 서버
cd drf-server && python manage.py runserver

# FastAPI WebSocket 서버
cd fastapi-server && uvicorn websocket:app --port 8001 --reload
```

---

### [ 1 ] 라우팅 기본 동작

- [ ] `http://localhost:8000/` 접속 시 `http://localhost:8000/dashboard/` 로 302 리다이렉트 되는지 확인
- [ ] `http://localhost:8000/dashboard/` 에서 대시보드 페이지가 정상 렌더되는지 확인
- [ ] `http://localhost:8000/accounts/login/` 에서 로그인 페이지가 정상 렌더되는지 확인
- [ ] `http://localhost:8000/dashboard/safety/checklist/` 에서 안전확인 페이지가 정상 렌더되는지 확인
- [ ] 브라우저 콘솔에 404 / `ReferenceError` 가 없는지 확인

---

### [ 2 ] 인증 플로우 (accounts)

- [ ] 로그인 폼 제출 → `POST /accounts/api/auth/login/` 200 응답 확인
- [ ] 응답의 `access_token` 이 `localStorage` 에 저장되는지 확인
- [ ] 페이지 로드 시 `GET /accounts/api/auth/me/` 호출 및 200 응답 확인
- [ ] 헤더에 로그인 유저명이 표시되는지 확인
- [ ] 토큰 없이 `/dashboard/` 접근 시 `/accounts/login/` 으로 리다이렉트되는지 확인
- [ ] 로그아웃 확인 클릭 시 `localStorage` 클리어 후 `/accounts/login/` 이동 확인

---

### [ 3 ] 대시보드 API (dashboard)

- [ ] 새로고침 버튼 클릭 → `GET /dashboard/api/refresh/` 200 응답 확인
- [ ] 관리자 계정으로 로그인 시 관리자 버튼이 표시되는지 확인
- [ ] SNB 메뉴 `GET /dashboard/api/menu/` 호출 후 메뉴 트리가 렌더되는지 확인
- [ ] 홈 버튼 클릭 시 `/dashboard/` 로 이동하는지 확인 (대시보드에서 클릭하면 새로고침)

---

### [ 4 ] 알람 API (alarms)

- [ ] `GET /alarms/api/` 호출 시 알람 목록 응답 확인
- [ ] `GET /alarms/api/summary/` 호출 시 `last_24h_danger` / `last_24h_warning` 응답 확인
- [ ] 이벤트 현황 패널에 최근 10건이 표시되는지 확인
- [ ] 24시간 요약 카운트(위험 N건 / 주의 N건)가 표시되는지 확인
- [ ] `GET /alarms/api/my-status/` 호출 시 작업자 상태 응답 확인
- [ ] `GET /alarms/api/worker-summary/` 호출 시 관리자 KPI 응답 확인

---

### [ 5 ] WebSocket 실시간 연동

- [ ] `ws://127.0.0.1:8001/ws/sensors/` 연결 후 wsStatus 배지 "● 실시간 연결" 확인
- [ ] 가스 데이터 수신 시 패널 12 테이블이 업데이트되는지 확인
- [ ] `level === '위험'` 수신 시 알림 팝업 + 이벤트 목록에 항목이 추가되는지 확인
- [ ] WS 연결 끊김 후 5초 내 자동 재연결되는지 확인

---

### [ 6 ] SNB 사이드바

- [ ] 햄버거 버튼 클릭 → SNB drawer 열림 확인
- [ ] SNB 내 "작업 전 안전 확인" 클릭 → `/dashboard/safety/checklist/` 이동 확인
- [ ] 안전확인 페이지의 "나의 안전 확인 바로가기" 버튼 → `/dashboard/safety/checklist/` 확인
- [ ] 오버레이 클릭 / 닫기 버튼으로 SNB 닫힘 확인

---

### [ 7 ] Django Admin

- [ ] `http://localhost:8000/admin/` 접속 시 Django 관리자 페이지 정상 렌더 확인

---

## 8. 변경사항 비교 (Before / After)

| 구분 | v6 | v7 |
|------|----|----|
| 루트 `/` 처리 | 대시보드 직접 렌더 | 302 redirect → `/dashboard/` |
| URL 네임스페이스 | 앱 구분 없이 평탄 | **앱 접두사** (`accounts/` · `dashboard/` · `alarms/`) |
| alarms 라우터 등록명 | `r"alarms"` → `/api/alarms/alarms/` (중복) | `r""` → `/alarms/api/` (간결) |
| JS 하드코딩 경로 수정 파일 | 없음 | **5개** (auth.js · layout.js · event-panel.js · worker-panel.js · main_dashboard.html) |
| 대시보드 refresh URL | `/api/dashboard/refresh/` | `/dashboard/api/refresh/` (단축) |
