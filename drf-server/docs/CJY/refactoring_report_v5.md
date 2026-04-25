# 리팩토링 보고서 v5 — 파일 정리 / 기능 통합 / URL 구조 개편 계획

> 작성일: 2026-04-17
> 브랜치: `feature/snb_header.v1`
> 기준 문서: `docs/refactoring_report_v4.md` (dashboard.js 모듈 분리)

---

## 1. 요약 (Summary)

v4 이후 팀원별 작업본(`dashboard_jh.html`, `dashboard_sh.html`, `dashboard_CJY.html`)이 별도 파일로 남아 있었습니다.
이번 v5 작업에서는 세 가지 큰 작업을 진행했습니다.

1. **기능 통합** — 각 작업본에 추가된 기능을 `main_dashboard.html` / refactors 모듈로 병합
2. **파일 정리** — 역할이 없어진 HTML·JS·CSS 파일을 `delete_backup` 폴더로 격리
3. **템플릿 디렉터리 구조화** — 역할별 하위 폴더로 분류

이어서 진행 예정인 **URL 구조 개편 (dashboard 앱 신규 생성)** 계획도 함께 기록합니다.

---

## 2. 기능 통합 내역

### 2-1. dashboard_jh.html + main_jh.js → 반영된 내용

`dashboard_jh.html` / `main_jh.js`는 `main_dashboard.html`의 개인 작업본으로, 아래 기능이 추가되어 있었습니다.

| 기능 | 반영 파일 | 비고 |
|------|-----------|------|
| SNB 메뉴 아이콘 이모지 → SVG 교체 | `js/refactors/layout.js` `iconMap` | Material Design SVG |
| `renderUser()` 분리 출력 | `layout.js` 유지 | `headerUsername` + `headerRole` 별도 요소로 한 줄 표시 |

> 그 외 Auth·SNB·Menu·Header·initApp 로직은 v4에서 이미 refactors로 분리 완료된 것과 동일하여 반영 제외

### 2-2. alarm_panel.html → main_dashboard.html 이식 후 제거

`alarm_panel.html`은 독립 페이지였으나, 해당 기능 전체를 main에 통합한 뒤 URL 및 파일 모두 제거했습니다.

| 기능 | 이식 위치 | 비고 |
|------|-----------|------|
| 이벤트 현황 동적 로드 (`/api/alarms/`) | `js/refactors/event-panel.js` 신규 생성 | 최근 10건 로드 |
| 24시간 요약 카운트 (`/api/alarms/summary/`) | `event-panel.js` | `summary-danger` / `summary-warning` |
| CM-07 알림 팝업 | 기존 `alarm-popup.js` 그대로 사용 | 이미 main에 포함됨 |
| WebSocket 위험 수신 시 이벤트 목록 실시간 추가 | `js/refactors/websocket.js` | `EventPanel.addItem()` 연동 |

**이벤트 현황 패널 HTML 변경 (`main_dashboard.html`)**

```html
<!-- Before: 하드코딩 더미 -->
<div class="event-item">홍길동 작업자 ...</div>
<div class="event-summary">위험 2건 / 주의 1건</div>

<!-- After: API 동적 로드 -->
<div class="event-summary">
  위험 <span id="summary-danger">0</span>건
  / 주의 <span id="summary-warning">0</span>건
</div>
<div id="event-list">
  <div id="event-empty">현재 발생한 이벤트가 없습니다</div>
</div>
```

---

## 3. 파일 정리 내역

### 3-1. delete_backup으로 격리된 파일

| 파일 | 이유 |
|------|------|
| `templates/dashboard_jh.html` | 개인 작업본, main_dashboard로 통합 |
| `templates/dashboard_sh.html` | 개인 작업본, main_dashboard로 통합 |
| `templates/dashboard_CJY.html` | 개인 작업본, main_dashboard로 통합 |
| `templates/dashboard_backup.html` | urls.py에 등록되지 않은 백업본 |
| `static/js/main_jh.js` | `dashboard_jh.html` 전용 |
| `static/js/main.js` | `dashboard_sh.html` / `dashboard_CJY.html` 전용 |
| `static/js/CJY.js` | `dashboard_CJY.html` 전용 |
| `static/js/dashboard.js` | v4 분리 전 원본, 현재 로드되지 않음 |
| `static/js/util.js` | `js/refactors/util.js`로 대체 |
| `static/css/style.css` | 개인 작업본 전용, main은 `dashboard.css` + `header.css` 사용 |
| `static/css/CJY.css` | `dashboard_CJY.html` 전용 |

### 3-2. urls.py에서 제거된 항목

| 제거 항목 | 이유 |
|-----------|------|
| `dashboard_jh` 뷰 + `dashboard_jh/` path | 개인 대시보드 |
| `dashboard_sh` 뷰 + `dashboard_sh/` path | 개인 대시보드 |
| `dashboard_cjy` 뷰 + `dashboard-cjy/` path | 개인 대시보드 |
| `alarm_panel` 뷰 + `alarm/` path | 기능 전체를 main에 이식 후 제거 |

---

## 4. 템플릿 디렉터리 구조화

역할별 하위 폴더로 재구성했습니다.

**Before**
```
templates/
├── main_dashboard.html
├── header.html
├── alarm_popup.html
├── login.html
└── safety_checklist.html
```

**After**
```
templates/
├── main_dashboard.html        ← 메인 페이지 (루트 유지)
├── auth/
│   └── login.html             ← 인증 관련 페이지
├── components/                ← {% include %} 전용 컴포넌트
│   ├── header.html
│   └── alarm_popup.html
└── snb_details/               ← SNB 사이드바 진입 페이지
    └── safety_checklist.html
```

**함께 수정된 참조 경로**

| 파일 | 변경 전 | 변경 후 |
|------|---------|---------|
| `urls.py` | `render(request, "login.html")` | `render(request, "auth/login.html")` |
| `urls.py` | `render(request, "safety_checklist.html")` | `render(request, "snb_details/safety_checklist.html")` |
| `main_dashboard.html` | `{% include 'header.html' %}` | `{% include 'components/header.html' %}` |
| `main_dashboard.html` | `{% include 'alarm_popup.html' %}` | `{% include 'components/alarm_popup.html' %}` |
| `safety_checklist.html` | `{% include 'header.html' %}` | `{% include 'components/header.html' %}` |
| `safety_checklist.html` | `{% include 'alarm_popup.html' %}` | `{% include 'components/alarm_popup.html' %}` |

**safety_checklist.html URL 변경**

| 변경 전 | 변경 후 |
|---------|---------|
| `dashboard_jh/safety/checklist/` | `safety/checklist/` |
| name: `safety-checklist-jh` | name: `safety-checklist` |

---

## 5. 신규 모듈 — event-panel.js

`js/refactors/event-panel.js` 신규 생성

| 메서드 | 역할 |
|--------|------|
| `EventPanel.init()` | 페이지 로드 시 이벤트 목록 + 요약 초기 로드 |
| `EventPanel.loadEventList()` | `/api/alarms/?ordering=-created_at&limit=10` 호출 |
| `EventPanel.loadSummary()` | `/api/alarms/summary/` 호출 → 24시간 위험/주의 카운트 |
| `EventPanel.addItem(data)` | 이벤트 항목 DOM 추가 (WebSocket 실시간 연동 포함) |

**로드 순서 추가 (`main_dashboard.html`)**
```
② 독립 모듈 그룹에 추가:
   auth.js → alarm-popup.js → event-panel.js → gas-panel.js → ...
```

**`app.js` 변경**
```js
// 추가
EventPanel.init();
```

**`websocket.js` 변경**
```js
// 위험 수신 시 AlarmPopup과 EventPanel 동시 연동
AlarmPopup.show(alarmData);
EventPanel.addItem(alarmData);   // 추가
```

---

## 6. 다음 작업 계획 — URL 구조 개편 (dashboard 앱 신규 생성)

### 6-1. 현재 문제

`config/urls.py`가 뷰 함수 정의 + URL 라우팅을 동시에 담당하고 있습니다.
`accounts/views.py`에 인증과 무관한 대시보드 뷰(`MenuView`, `DashboardRefreshView`)가 섞여 있습니다.

### 6-2. 목표 구조

`config/urls.py`는 **순수 라우터** 역할만 합니다.

```python
# config/urls.py (목표)
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.dashboard.urls")),
    path("api/alarms/", include("apps.alarms.urls")),
]
```

### 6-3. 앱별 책임 분리

| 앱 | 담당 URL | 담당 뷰 |
|----|----------|---------|
| `accounts` | `login/`, `api/auth/*` | `LoginView`, `MeView`, `TokenRefreshView`, `login_page` 렌더 |
| `dashboard` | `/`, `dashboard/`, `safety/checklist/`, `api/menu/`, `api/dashboard/refresh/` | `main_dashboard` 렌더, `safety_checklist_page` 렌더, `MenuView`, `DashboardRefreshView` |
| `alarms` | `api/alarms/*` | `AlarmRecordViewSet`, `MyStatusView`, `WorkerSummaryView` |

### 6-4. 작업 항목

- [ ] `apps/dashboard/` 앱 신규 생성 (`views.py`, `urls.py`, `apps.py`)
- [ ] `accounts/views.py`의 `MenuView`, `DashboardRefreshView` → `dashboard/views.py`로 이동
- [ ] `accounts/urls.py`에 `login/` 페이지 렌더 라우트 추가
- [ ] `dashboard/urls.py` 작성 (HTML + API 라우트 포함)
- [ ] `config/urls.py` 순수 라우터로 교체
- [ ] `config/settings.py` `INSTALLED_APPS`에 `apps.dashboard` 등록

---

## 7. 변경사항 비교 (Before / After)

| 구분 | v4 | v5 |
|------|----|----|
| 활성 HTML 파일 수 | 8개 (개인 작업본 포함) | **4개** (main, login, safety_checklist, components 2개) |
| 활성 JS 파일 수 (`static/js/`) | 5개 + refactors 10개 | **refactors 11개만** (event-panel.js 추가) |
| 활성 CSS 파일 수 | 4개 | **2개** (dashboard.css, header.css) |
| 템플릿 구조 | 단일 폴더 | **역할별 3개 하위 폴더** (auth / components / snb_details) |
| config/urls.py 뷰 정의 수 | 7개 | **3개** (main_dashboard, login_page, safety_checklist_page) |
| 이벤트 현황 패널 | 하드코딩 더미 | **API 동적 로드** |
