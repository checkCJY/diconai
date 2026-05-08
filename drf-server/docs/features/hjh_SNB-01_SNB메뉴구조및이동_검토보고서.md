# SNB-01 SNB 메뉴 구조 및 이동 — 코드 검토 보고서

> 작성자: 한지혜 / 작성일: 2026-04-24
> 대상 기능 ID: **SNB-01** (SNB 메뉴 구조 및 이동)
> 검토 범위: 프론트엔드 + 백엔드 전체

---

## 1. 기능 정의서 스펙 요약

| 항목 | 내용 |
|------|------|
| 기능 목적 | 좌측 메뉴 기반 상세 화면 이동 |
| 사용자 시나리오 | 햄버거 클릭 → Depth1 메뉴 노출 → 하위 메뉴 펼침 → 메뉴 선택 시 상세화면 이동 |
| 수집 정보 | 메뉴 트리, 권한 |
| 디자인 요소 | 좌측 Drawer, 아이콘, **활성 메뉴 하이라이트** |
| 유효성 처리 | **권한 없는 메뉴 비노출** |
| 예외 조건 | **메뉴 overflow 시 스크롤** |
| 에러 처리 | **메뉴 조회 실패 안내** |
| 백엔드 처리 | 권한기반 메뉴 트리 조회 |
| 프론트엔드 처리 | SNB open/close, **accordion**, **active 상태** |
| 참고사항 | **Depth1: 나의 안전확인, 모니터링** |

---

## 2. 검토 대상 파일

| 역할 | 파일 경로 |
|------|-----------|
| SNB HTML 구조 | `templates/components/header.html` |
| SNB 토글 / 메뉴 렌더링 / 아코디언 | `static/js/refactors/layout.js` |
| 작업자 현황 패널 (상세 보기 버튼) | `static/js/refactors/worker-panel.js` |
| SNB / Drawer 스타일 | `static/css/components/header.css` |
| 권한별 메뉴 트리 정의 | `apps/dashboard/menu.py` |
| 메뉴 API | `apps/dashboard/views.py` |
| 대시보드 URL 라우팅 | `apps/dashboard/urls.py` |
| 전체 URL 라우팅 | `config/urls.py` |

---

## 3. 스펙 충족 항목 ✅

| 항목 | 구현 위치 | 비고 |
|------|-----------|------|
| 햄버거 클릭 → SNB 열림/닫힘 | `layout.js` — `SNB.toggle()` | 토글 로직 |
| Depth1 메뉴 + 아이콘 노출 | `layout.js` — `iconMap` SVG | shield / monitor / settings |
| 아이콘 미정의 fallback | `layout.js` — `iconMap[icon] \|\| '•'` | |
| Depth2 아코디언 펼침/접힘 | `layout.js` — `.expanded` / `.open` 클래스 | CSS transition 적용 |
| Depth2 클릭 → 페이지 이동 | `layout.js` — `<a href>` 방식 | |
| Depth2 클릭 시 SNB 자동 닫힘 | `layout.js` — `SNB.close()` 이벤트 | |
| 활성 메뉴 하이라이트 | `layout.js` — `currentPath === child.path` → `.active` | 파란 border-left |
| 현재 경로 포함 Depth1 자동 펼침 | `layout.js` — `menu.children.some(...)` | 페이지 진입 시 자동 |
| 권한별 메뉴 분기 | `menu.py` — `get_menu_tree(role)` | facility_admin / super_admin 추가 메뉴 |
| 권한 없는 메뉴 비노출 | `menu.py` — 역할별 조건부 반환 | |
| 메뉴 overflow 스크롤 | `header.css` — `.snb-menu { overflow-y: auto }` | SNB 전체 스크롤 |
| 메뉴 조회 실패 안내 | `header.html` — `#snbError` / `layout.js` — `Menu.showError()` | |
| Depth1: 나의 안전확인 / 모니터링 | `menu.py` — `_MENU_WORKER` | 참고사항 충족 |

---

## 4. 문제 항목 — 심각도별 분류

### 🟡 MEDIUM — 운영 전 수정 권장

---

#### M-1. `worker-panel.js` 상세 보기 URL이 SNB 메뉴 경로와 불일치 → **수정 완료 (2026-04-24)**

**위치:** `static/js/refactors/worker-panel.js:94`

**문제 흐름:**

```
[대시보드 작업자 현황 패널 "상세 보기" 클릭]
  → worker-panel.js:94
  → window.location.href = '/monitoring/workers'   ← 잘못된 경로

[SNB 메뉴 "작업자 현황" 클릭]
  → menu.py SNB-09: "/dashboard/monitoring/workers/"  ← 올바른 경로
```

**URL 경로 비교:**

| 진입 경로 | URL | 결과 |
|-----------|-----|------|
| SNB-09 메뉴 클릭 | `/dashboard/monitoring/workers/` | ✅ 200 OK |
| 대시보드 상세 보기 클릭 (수정 전) | `/monitoring/workers` | ❌ 404 |
| 대시보드 상세 보기 클릭 (수정 후) | `/dashboard/monitoring/workers/` | ✅ 200 OK |

**확인:** `config/urls.py`에서 `/monitoring/` 프리픽스는 `apps.monitoring.urls_cjy`로 연결됩니다. `urls_cjy.py`에 등록된 경로:

```python
# apps/monitoring/urls_cjy.py — /monitoring/workers 없음
path("api/power/event/", ...)
path("api/power/data/", ...)
path("api/power/onoff/", ...)
path("api/power/current/", ...)
path("api/power/voltage/", ...)
path("api/power/watt/", ...)
```

`/monitoring/workers`는 어디에도 등록되어 있지 않아 실제 404가 발생합니다.

---

### 🟢 LOW — 장기 개선 고려

---

#### L-1. `.snb-overlay` CSS transition이 실제로 동작하지 않음

**위치:** `static/css/components/header.css:55-56`

```css
.snb-overlay { display: none; opacity: 0; transition: opacity .25s; }
.snb-overlay.open { display: block; opacity: 1; }
```

CSS `transition`은 `display: none` → `display: block` 전환 시 동작하지 않아 오버레이가 서서히 나타나지 않고 즉시 나타납니다. **기능에는 영향 없음.** SNB Drawer 자체는 `transform` transition으로 부드럽게 동작하므로 UX 체감 차이가 미미합니다.

**현재 유지 결정.** 수정하려면 `display: none` → `visibility: hidden + pointer-events: none` 방식으로 변경하면 됩니다.

---

#### L-2. Depth2 `max-height: 400px` — 현재 구조에서 문제 없음

**위치:** `static/css/components/header.css:79`

```css
.snb-depth2.open { max-height: 400px; }
```

처음에는 항목 추가 시 잘릴 위험이 있다고 판단했으나, 재검토 결과 **현재 구조에서 문제 없음**으로 변경합니다.

이유:
- 현재 최대 Depth2 항목(모니터링 5개) × 36px = 180px. 400px에 충분한 여유
- `.snb-menu { overflow-y: auto }` — SNB 전체 스크롤이 보장되어 실제 잘림 없음
- `max-height: 9999px`로 변경 시 `transition: max-height .25s`가 사실상 무효화되어 아코디언 애니메이션이 사라지는 부작용 발생

**현재 400px 유지가 올바른 선택입니다.**

---

## 5. 종합 요약

| 구분 | 항목 수 | 항목 |
|------|---------|------|
| ✅ 충족 | 13개 | SNB 토글, Depth1 노출, 아이콘, fallback, 아코디언, 페이지 이동, SNB 자동 닫힘, active 하이라이트, 자동 펼침, 권한 분기, overflow 스크롤, 에러 안내, Depth1 구성 |
| 🟡 MEDIUM | 1개 | M-1 상세보기 URL 404 |
| 🟢 LOW | 2개 | L-1 overlay transition, L-2 max-height (현재 구조에서 문제 없음 확인) |

> M-1은 **2026-04-24 수정 완료.**

---

## 6. 수정 우선순위 Action Items

| 순서 | 항목 | 담당 | 예상 공수 | 기한 |
|------|------|------|-----------|------|
| 1 | L-1 overlay transition CSS 개선 | 프론트 | 5min | 여유 시 |

---

## 7. 잘 구현된 부분 (유지)

- **컴포넌트 분리:** `header.html` 단일 파일로 SNB 전체 구조를 관리, 모든 페이지 `{% include %}`로 재사용
- **동적 메뉴 렌더링:** 서버에서 받은 `menu_tree` 기반으로 DOM을 동적 생성 — 메뉴 항목 추가 시 JS 수정 없이 `menu.py`만 변경
- **현재 경로 기반 active/자동 펼침:** `window.location.pathname`으로 새로고침 후에도 현재 메뉴가 하이라이트되고 자동으로 펼쳐짐
- **아이콘 일관성:** 이모지 대신 Material Design SVG — OS/브라우저 무관하게 동일 렌더링
- **아이콘 fallback:** `iconMap[menu.icon] || '•'` — 정의되지 않은 아이콘도 렌더링 오류 없음
- **서버사이드 권한 분기:** 메뉴 필터링이 프론트가 아닌 서버(`menu.py`)에서 처리 — 클라이언트 임의 조작 차단
- **`copy.deepcopy`:** 메뉴 트리를 복사본으로 반환해 원본 수정 방지
- **오버레이 닫기:** SNB 외부(오버레이) 클릭 시 닫힘 처리로 직관적 UX
- **에러 상태 분리:** `#snbMenu`(성공)와 `#snbError`(실패)를 별도 요소로 관리

---

## 8. 수정 이력 (2026-04-24)

> 검토 보고서 작성 후 MEDIUM 1건 수정 완료.

---

### M-1 수정 — 작업자 현황 상세 보기 URL 404 수정

**수정 파일:** `static/js/refactors/worker-panel.js:94`

| 단계 | 내용 |
|------|------|
| 원인 | SNB 메뉴 경로는 `/dashboard/monitoring/workers/`이나 상세 보기 버튼은 `/monitoring/workers`로 하드코딩 |
| 영향 | `/monitoring/workers`가 `urls_cjy.py`에 미등록 → 클릭 시 404 반환 |
| 수정 | `/monitoring/workers` → `/dashboard/monitoring/workers/` |

```javascript
// 수정 전
window.location.href = '/monitoring/workers';

// 수정 후
window.location.href = '/dashboard/monitoring/workers/';
```

**검증:**
- `dashboard/urls.py`에 `path("monitoring/workers/", views.monitoring_workers_page, ...)` 등록 확인 ✅
- SNB-09 메뉴 경로(`menu.py`)와 동일 ✅

---

## 메뉴 구성 현황 (최종)

### worker / viewer 메뉴

| Depth1 | Depth2 ID | Depth2 라벨 | 경로 |
|--------|-----------|------------|------|
| 나의 안전확인 | SNB-02 | 작업 전 안전 확인 | `/dashboard/safety/checklist/` |
| 나의 안전확인 | SNB-04 | 안전 확인 이력 | `/dashboard/safety/history/` |
| 모니터링 | SNB-06 | 실시간 모니터링 | `/dashboard/monitoring/realtime/` |
| 모니터링 | SNB-07 | 실시간/AI 예측 유해가스 현황 | `/dashboard/monitoring/gas/` |
| 모니터링 | SNB-08 | 실시간/AI 예측 스마트 전력 현황 | `/dashboard/monitoring/power/` |
| 모니터링 | SNB-09 | 작업자 현황 | `/dashboard/monitoring/workers/` |
| 모니터링 | SNB-10 | 이벤트 현황 | `/dashboard/monitoring/events/` |

### facility_admin / super_admin 추가 메뉴

| Depth1 | Depth2 ID | Depth2 라벨 | 경로 | 비고 |
|--------|-----------|------------|------|------|
| 관리자 전용 | SNB-05 | 전체 이력 현황 | `/dashboard/admin/` | SNB-05 구현 시 전용 URL로 교체 필요 |

> SNB-03 (VR 교육)은 체크리스트 완료 후 자동 이동하는 플로우로, SNB 메뉴에서 직접 접근하지 않는 설계. 미노출이 의도된 동작.
