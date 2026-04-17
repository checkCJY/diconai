# 리팩토링 보고서 v8 — 경로 오류 일괄 수정

작성일: 2026-04-17
작업자: han jihye
브랜치: feature/snb_header.v1

---

## 개요

1차 리팩토링 이후 `config/urls.py` 및 각 앱의 `urls.py`와 실제 JS·템플릿 코드 사이에서
발견된 URL/경로 불일치 문제 5건을 수정하였습니다.

---

## 수정 내역

### [BUG-01] `auth.js` — `/me/` API 경로 오류

| 항목 | 내용 |
|------|------|
| 파일 | `static/js/refactors/auth.js:32` |
| 문제 | `Auth.getMe()`가 `/accounts/api/auth/me/`를 호출 — 존재하지 않는 경로 |
| 원인 | `config/urls.py`에서 accounts API는 `api/auth/` 프리픽스로 등록 → 실제 경로는 `/api/auth/me/` |
| 영향 | `getMe()` 항상 null 반환 → SNB 메뉴 전체 렌더링 실패, "메뉴를 불러올 수 없습니다." 표시 |

```diff
- const res = await this.apiFetch('/accounts/api/auth/me/');
+ const res = await this.apiFetch('/api/auth/me/');
```

---

### [BUG-02] `worker-panel.js` — localStorage 키 이름 불일치

| 항목 | 내용 |
|------|------|
| 파일 | `static/js/refactors/worker-panel.js:93` |
| 문제 | `localStorage.getItem('user_type')` 조회 — 해당 키는 저장된 적 없음 |
| 원인 | 로그인 처리(`login.html`, `accounts/views.py`)에서 `role` 키로 저장하지만 worker-panel에서 `user_type` 키로 읽음 |
| 영향 | `isAdmin`이 항상 `false` → 관리자 계정으로 로그인해도 Admin View(KPI 카드)가 아닌 Worker View(상태 바)만 표시 |

```diff
- const isAdmin = (localStorage.getItem('user_type') || 'worker') === 'admin';
+ const isAdmin = (localStorage.getItem('role') || 'worker') === 'admin';
```

---

### [BUG-03] `worker-panel.js` — 상세 보기 링크 잘못된 URL

| 항목 | 내용 |
|------|------|
| 파일 | `static/js/refactors/worker-panel.js:90` |
| 문제 | `'+ 상세 보기'` 클릭 시 `/snb-09/`로 이동 — 등록된 URL 없음 |
| 원인 | 리팩토링 과정에서 내부 코드명(`SNB-09`)이 URL에 그대로 사용됨 |
| 영향 | 클릭 시 404 Not Found |
| 참고 | `apps/dashboard/menu.py`에서 SNB-09 = 작업자 현황 = `/monitoring/workers` |

```diff
- document.getElementById('mn04-btn-detail')?.addEventListener('click', () => { window.location.href = '/snb-09/'; });
+ document.getElementById('mn04-btn-detail')?.addEventListener('click', () => { window.location.href = '/monitoring/workers'; });
```

---

### [BUG-04] `menu.py` — SNB-02 경로 trailing slash 누락

| 항목 | 내용 |
|------|------|
| 파일 | `apps/dashboard/menu.py:12` |
| 문제 | SNB-02 경로가 `/safety/checklist` (trailing slash 없음) |
| 원인 | `apps/dashboard/urls.py`에 `path("safety/checklist/", ...)` — trailing slash 있음 |
| 영향 | Django `APPEND_SLASH=True`로 자동 리다이렉트되지만 불필요한 302 응답 발생, active 메뉴 감지 로직(`currentPath === child.path`)도 불일치 |

```diff
- {"id": "SNB-02", "label": "작업 전 안전 확인", "path": "/safety/checklist"},
+ {"id": "SNB-02", "label": "작업 전 안전 확인", "path": "/safety/checklist/"},
```

---

### [BUG-05] `safety_checklist.html` — 불필요한 스크립트 로드 및 잘못된 초기화

| 항목 | 내용 |
|------|------|
| 파일 | `templates/snb_details/safety_checklist.html` |
| 문제 | 대시보드 전용 스크립트 7개를 전부 로드한 뒤 `app.js`가 `initCharts()`, `MapPanel.init()`, `initWebSocket()` 호출 |
| 원인 | 안전확인 페이지에는 차트 canvas, Leaflet 맵, 작업자 현황 패널 DOM이 존재하지 않음. 특히 `initWebSocket()`은 FastAPI WebSocket 서버에 불필요한 연결 시도 |
| 영향 | 불필요한 JS 파일 다운로드 + WebSocket 연결 시도 (콘솔 에러 발생) |

**수정 전 로드 목록 (10개):**
```
util.js / auth.js / alarm-popup.js / event-panel.js / charts.js
map-panel.js / layout.js / worker-panel.js / websocket.js / app.js
```

**수정 후 로드 목록 (4개 + 인라인 init):**
```
util.js / auth.js / alarm-popup.js / layout.js / <inline initPage>
```

인라인 `initPage()`는 `app.js`와 동일한 인증·헤더·SNB 초기화를 수행하되
대시보드 전용 모듈(`initCharts`, `MapPanel`, `initWebSocket`, `EventPanel`)은 호출하지 않습니다.

---

## 수정 파일 목록

| 파일 | 수정 종류 |
|------|-----------|
| `static/js/refactors/auth.js` | BUG-01: API URL 수정 |
| `static/js/refactors/worker-panel.js` | BUG-02: localStorage 키 수정, BUG-03: 상세 보기 URL 수정 |
| `apps/dashboard/menu.py` | BUG-04: trailing slash 추가 |
| `templates/snb_details/safety_checklist.html` | BUG-05: 불필요 스크립트 제거 및 인라인 init 적용 |

---

## URL 경로 최종 정리

| URL | 뷰 | 비고 |
|-----|----|------|
| `/accounts/login/` | `login_page` | HTML 페이지 |
| `/api/auth/login/` | `LoginView` | JWT 발급 |
| `/api/auth/me/` | `MeView` | 사용자 정보 + 메뉴 트리 |
| `/api/auth/token/refresh/` | `TokenRefreshView` | 토큰 갱신 |
| `/dashboard/` | `main_dashboard` | 대시보드 메인 |
| `/dashboard/safety/checklist/` | `safety_checklist_page` | 안전확인 페이지 |
| `/dashboard/api/menu/` | `MenuView` | 메뉴 API |
| `/dashboard/api/refresh/` | `DashboardRefreshView` | 갱신 API |
| `/alarms/api/` | `AlarmRecordViewSet` list | 이벤트 목록 |
| `/alarms/api/summary/` | `AlarmRecordViewSet.summary` | 24h 요약 |
| `/alarms/api/my-status/` | `MyStatusView` | 내 위험도 |
| `/alarms/api/worker-summary/` | `WorkerSummaryView` | 전체 작업자 요약 |
