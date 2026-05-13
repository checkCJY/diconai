# 변경 기록서 — 대쉬보드/어드민 UI 정리 + 로딩 상태 일관화

> 작성일: 2026-05-06
> 브랜치: feature/project_4_refactoring
> 커밋 (3건):
> - `ec217a3` refactor : 관리자 페이지 사이드바 및 로고 추가
> - `e74bd49` refactor : 가스쪽 스켈레톤 적용 수정
> - `ea45b1b` fix : 유해가스 차트부분 통일
>
> 작업 종류: refactor + fix (UI/UX 정리)
> 하위 호환성: **non-breaking** — 외부 API/스키마/env 변경 없음. WS 페이로드의 `total_power_kw`/`power_change_pct`가 stale 상태에서 기존 더미값 → `null`로 바뀜(프론트 측 null-safe 갱신 동시 적용). 어드민 사이드바 전면 마크업 교체(자동 상속, 9개 어드민 페이지 무영향).

---

## 1. 변경 개요

- **목적(Why):**
  - 어드민 패널 사이드바가 70px 아이콘 전용 고정폭이라 한글 라벨("전력 시스템"·"안전 정책/기준 관리")이 잘려 가독성 저하. 메인 대쉬보드처럼 토글 가능한 드로어로 통일 필요.
  - 대쉬보드/어드민/로그인 모두 자리표시 텍스트("LOGO"/"로고"/방패 SVG)를 사용 중. 실제 로고 이미지 적용 필요.
  - 가스 패널이 페이지 로드 직후 별도 init JS가 스켈레톤을 즉시 텍스트("연결 중...")로 덮어쓰고, WS의 `gas_loading: true` 상태에서도 "데이터가 존재하지 않습니다" 메시지로 테이블을 비워 전력 패널과 동작이 어긋남(전력은 스켈레톤 유지). 동일 패턴으로 통일.
  - 가스 패널 테이블이 기본 `.tbl` (font-size 11px / padding 2-3px)을 쓰는 반면 전력 패널은 `#powerPanel`로 더 큰 padding·sticky thead·둥근 모서리 적용. 두 패널 시각 정렬 필요.
  - WS 페이로드가 stale일 때 backend가 하드코드 더미값(`1200~1300 kW`)을 송신해 더미 미가동 시에도 KPI에 가짜 숫자가 표시됨. `null`로 송신해 프론트가 로딩/공백을 유지하도록 변경.
  - "전체 사용량" 차트(kW 단위)와 채널별 차트(W 단위)가 같은 Y축·임계치를 공유해 단위 부정합. 페이지별 적정 단위로 분리.
  - 헤더 사용자 표시 "{username}님" → 환영 인사 톤으로 보강 요청.
  - WARNING 알람 카운트다운이 5초로 너무 짧아 작업자가 인지·대응할 시간 부족.

- **결과(What):**
  - 어드민 사이드바: `app-container` flex 해제, `position:fixed` 240px 드로어로 전환 + 햄버거 토글 + 백드롭 오버레이. 9개 어드민 페이지 자동 상속.
  - 로고: 대쉬보드 헤더·어드민 토픽바·로그인 페이지 모두 `static/img/logo.jpg` 적용. 로그인 뱃지 텍스트 "로고" → "산재 예방 통합 관제 플랫폼"으로 변경하면서 외부 라벨 제거.
  - 스켈레톤 일관화: `gas-panel.js` 삭제(스켈레톤 덮어쓰는 DOMContentLoaded 핸들러 한 가지뿐), `websocket.js`의 `data.gas_loading` 분기를 전력 패턴(`// FastAPI ... — skeleton 상태 그대로 유지`)으로 통일. backend도 stale 상태에서 `total_power_kw`/`power_change_pct: null` 송신.
  - 가스 테이블 시각 정렬: `#powerPanel .tbl ...` 4개 셀렉터에 `#gasPanel`을 함께 묶어 동일 스타일 적용.
  - 헤더 인사말: `${username}님` → `${username}님 환영합니다`.
  - 전력 차트 단위 분리: `POWER_CHART_Y_OPTS_KW`(10 kW step, suggestedMax 80) + 채널별 임계치 KW 상수 추가, `applyPowerChartUnit('kW' | 'W')`가 `_switchPowerChart(idx)`에서 idx 0(전체) vs 1+(채널별) 따라 호출.
  - 알람 WARNING 시간: 5초 → 10초.

- **영향 범위(Where):**
  - 프론트엔드: `static/css/admin.css`, `static/css/auth/login.css`, `static/css/components/header.css`, `static/css/dashboard.css`, `static/js/admin/main.js`, `static/js/dashboard/charts.js`, `static/js/dashboard/websocket.js`, `static/js/shared/layout.js`, `static/img/logo.jpg`(신규 자산), 다수 템플릿.
  - drf-server 백엔드(미미): `apps/alerts/tasks.py` 상수 1개.
  - fastapi-server: `websocket/services/broadcast.py`의 stale 시 더미값 → `null` 전환.
  - DB / 마이그레이션 / 환경변수: 변경 없음.

## 2. Before / After 비교

### 어드민 사이드바 (ec217a3)

| 구분 | Before | After |
|---|---|---|
| 마크업 | `<aside class="sidebar">` 고정폭 | `<div id="adminSnbOverlay">` + `<aside id="adminSnbDrawer" class="admin-snb-drawer">` |
| 레이아웃 | `app-container { display:flex }`, sidebar=flex 자식 70px | `app-container { display:block }`, sidebar=`position:fixed; transform:translateX(-100%)` 드로어, `main-wrapper { width:100% }` |
| 토글 | 없음 (항상 표시) | `<button id="adminHamburger" class="hamburger">☰</button>` + `AdminSNB.toggle()` (대쉬보드 `SNB` 패턴 미러) |
| 라벨 가독성 | 40x40 박스에 "전력 시스템"·"안전 정책/기준 관리" 잘림 | 드로어 폭 240px + `padding:10px 20px` + `text-overflow:ellipsis`로 풀라벨 노출 |
| 로고 위치 | 사이드바 내 자리표시 `<div class="brand-logo">로고</div>` | 토픽바 좌측에 `<a class="logo-link"><img src="logo.jpg" class="logo-img"></a>` |
| 중복 항목 | 부모 자리표시 `<a href="#">데이터</a>` + 실제 링크 "가스 데이터"/"전력 데이터" 함께 노출 | 자리표시 제거, 실제 링크만 |

### 로고 통일 (ec217a3)

| 위치 | Before | After |
|---|---|---|
| 대쉬보드 헤더 | `<div class="logo-box">LOGO</div>` (`56x30` 회색 박스) | `<img src="{% static 'img/logo.jpg' %}" alt="로고" class="logo-img">` (`height:30px; auto width`) |
| 어드민 토픽바 | (없음) | 햄버거 옆에 동일 `logo-img` 추가 |
| 로그인 뱃지 | 방패 SVG + "로고" 텍스트 + 뱃지 외부 `<div class="system-name">산재 예방 통합 관제 플랫폼</div>` | 뱃지 안에 `logo.jpg` (32x32 박스 fit) + "산재 예방 통합 관제 플랫폼" 텍스트, 외부 system-name 제거 |
| `logo.jpg` 자산 | 없음 | 신규 추가 (10,773 bytes, 400x400 RGB) |

### 가스 스켈레톤 일관화 (e74bd49)

| 구분 | Before | After |
|---|---|---|
| 페이지 로드 직후 | `gas-panel.js`의 DOMContentLoaded 핸들러가 KPI 스켈레톤을 "연결 중..." / "-" 텍스트로 즉시 덮어쓰기 | `gas-panel.js` 파일 삭제 + `main.html` 스크립트 태그 제거 → HTML 스켈레톤 그대로 노출 |
| `data.gas_loading: true` | `_setGasPanelError('데이터가 존재하지 않습니다.')` 호출 → 테이블 클리어, KPI '-' | `// FastAPI 가스 수신 대기 중 — skeleton 상태 그대로 유지` (전력 패턴 동일) |
| backend stale 시 | `total_power_kw = round(1200 + random.uniform(-50, 100))`, `power_change_pct = 0.0` 더미값 | `total_power_kw = None`, `power_change_pct = None` |
| 프론트 KPI 갱신 가드 | `if (powerTotal && data.total_power_kw !== undefined)` (null 통과 → `null.toLocaleString()` 에러 가능) | `if (powerTotal && data.total_power_kw != null)` (null/undefined 모두 차단) |
| AI 더미 필드 생성 | `total_power_kw`가 None이어도 `build_ai_dummy_fields()` 호출 → 산술 오류 위험 | `total_power_kw is not None`일 때만 호출, 아니면 빈 dict로 spread |

### 가스 테이블 시각 정렬 (ea45b1b)

| 구분 | Before | After |
|---|---|---|
| 가스 테이블 thead | 기본 `.tbl th` — color text2, padding 2-3px, sticky 없음 | `#powerPanel`과 동일 — sticky, bg `#1c2128`, padding 8x10, font 12px |
| 가스 테이블 td | 기본 `.tbl td` — padding 2x3, font 11px, 외곽 border 없음 | padding 8x10, font 12px, color `#e6edf3`, 행간 보더 + 마지막 행 보더 제거 |
| 적용 방식 | `#powerPanel .tbl ...` 4개 셀렉터가 전력 한정 | 동일 4개 셀렉터에 `#gasPanel`을 콤마 추가로 묶음 |

### 헤더 인사말 (e74bd49)

| Before | After |
|---|---|
| `${username}님` | `${username}님 환영합니다` |

### 전력 차트 단위 분리 (ec217a3)

| 구분 | Before | After |
|---|---|---|
| Y축 옵션 | `POWER_CHART_Y_OPTS` 1개 (W 단위 전제) | `POWER_CHART_Y_OPTS`(W) + `POWER_CHART_Y_OPTS_KW`(10kW step, suggestedMax 80) 분리 |
| 임계치 상수 | `POWER_THRESHOLD_WARNING=2200`, `_DANGER=2860` (W 단위 1세트) | 위 W 단위 + `POWER_TOTAL_THRESHOLD_WARNING_KW=35`, `_DANGER_KW=46` (16채널 동시 가정) 추가 |
| 차트 전환 | `_switchPowerChart(idx)`가 데이터만 교체 | `applyPowerChartUnit(idx === 0 ? 'kW' : 'W')` 선행 호출 — 단위·임계치·라벨 일괄 교체 |

### 알람 WARNING 카운트다운 (ec217a3)

| Before | After |
|---|---|
| `WARNING_DURATION_SEC = 5` | `WARNING_DURATION_SEC = 10` |

### 코드 차이 핵심

```js
// Before — gas-panel.js (전체 파일)
document.addEventListener('DOMContentLoaded', () => {
  const gasWorstName = document.getElementById('gasWorstName');
  const gasWorstRisk = document.getElementById('gasWorstRisk');
  if (gasWorstName) gasWorstName.textContent = '연결 중...';
  if (gasWorstRisk) gasWorstRisk.textContent = '-';
});

// After — 파일 삭제 (스켈레톤은 HTML에 이미 정의됨)
```

```python
# Before — broadcast.py: stale 시 하드코드 더미
if not equipment:
    total_power_kw = round(1200 + random.uniform(-50, 100))
    power_change_pct = 0.0

# After — None 송신 + AI 더미 필드 가드
if power_stale:
    total_power_kw = None
    power_change_pct = None
else:
    ...
ai_fields = (
    build_ai_dummy_fields(total_power_kw, equipment)
    if total_power_kw is not None
    else {}
)
```

```js
// Before — charts.js: 단일 Y축, 단일 임계치
function _switchPowerChart(idx) {
  if (!powerChart || !_aiPowerHist[idx]) return;
  const h = _aiPowerHist[idx];
  powerChart.data.labels = [...h.labels];
  ...
}

// After — 단위 전환 후 데이터 교체
function _switchPowerChart(idx) {
  if (!powerChart || !_aiPowerHist[idx]) return;
  applyPowerChartUnit(idx === 0 ? 'kW' : 'W');
  const h = _aiPowerHist[idx];
  ...
}
```

## 3. 변경 파일 목록

### 신규 (1개)
| 파일 | 역할 |
|---|---|
| `drf-server/static/img/logo.jpg` | 사이트 공통 로고 (400x400 RGB, 10,773 bytes). 헤더/어드민 토픽바/로그인 뱃지 3곳에서 사용. |

### 수정

#### 커밋 ec217a3 (관리자 사이드바 + 로고 + 부수 보강)
| 파일 | 변경 요약 |
|---|---|
| `drf-server/static/css/admin.css` | `.app-container` flex 제거, `.admin-snb-drawer`/`.admin-snb-overlay`/`.hamburger`/`.logo-img`/`.logo-link` 신규 룰. `.snb a` 40x40 → 풀폭 행 + ellipsis. `.brand-logo` 룰 삭제. `.main-wrapper` flex:1 → width:100% |
| `drf-server/static/css/auth/login.css` | `.logo-icon img { width:100%; height:100%; object-fit:cover; ... }` 1줄 추가 |
| `drf-server/static/css/components/header.css` | `.logo-box` (회색 박스) → `.logo-img { height:30px; width:auto; border-radius:4px; display:block; }` |
| `drf-server/static/js/admin/main.js` | `AdminSNB` 객체 추가 (open/close/toggle/init, 대쉬보드 `SNB` 패턴 미러) + `AdminSNB.init()` |
| `drf-server/static/js/dashboard/charts.js` | `POWER_TOTAL_THRESHOLD_WARNING_KW` / `_DANGER_KW` 상수 추가. `POWER_CHART_Y_OPTS_KW` 신규. `applyPowerChartUnit(unit)` 신규 |
| `drf-server/static/js/dashboard/websocket.js` | `_switchPowerChart`에서 `applyPowerChartUnit` 선행 호출. KPI 갱신 가드 `!== undefined` → `!= null` (null 안전) |
| `drf-server/templates/admin_panel/base.html` | `topbar-left`에 `<button id="adminHamburger">` + 로고 이미지 prepend |
| `drf-server/templates/auth/login.html` | 방패 SVG → `<img src="{% static 'img/logo.jpg' %}">`, "로고" → "산재 예방 통합 관제 플랫폼", 외부 `.system-name` 라인 제거 |
| `drf-server/templates/components/admin_sidebar.html` | `<aside class="sidebar">` → `<aside id="adminSnbDrawer" class="admin-snb-drawer">` + 앞에 오버레이 div. `<div class="brand-logo">` 삭제 |
| `drf-server/templates/components/header.html` | 1행 `{% load static %}` 추가, `<div class="logo-box">LOGO</div>` → `<img class="logo-img">` |
| `drf-server/apps/alerts/tasks.py` | `WARNING_DURATION_SEC = 5` → `10` (gas/power 알람 카운트다운 공통) |

#### 커밋 e74bd49 (가스 스켈레톤 일관화)
| 파일 | 변경 요약 |
|---|---|
| `drf-server/static/js/dashboard/websocket.js` | `data.gas_loading` 분기에서 `_setGasPanelError(...)` 호출 제거 → 빈 분기 + 주석 (skeleton 유지, 전력 패턴 동일) |
| `drf-server/static/js/shared/layout.js` | `${username}님` → `${username}님 환영합니다` |
| `drf-server/templates/dashboard/main.html` | `<script src="js/dashboard/panels/gas-panel.js">` 1줄 제거 |
| `fastapi-server/websocket/services/broadcast.py` | stale 시 `total_power_kw=None`/`power_change_pct=None` 송신. AI 더미 필드는 `total_power_kw`가 None이 아닐 때만 spread |

#### 커밋 ea45b1b (가스 테이블 정렬)
| 파일 | 변경 요약 |
|---|---|
| `drf-server/static/css/dashboard.css` | `#powerPanel .tbl ...` 4개 셀렉터에 `#gasPanel` 콤마 추가 (thead sticky, .tbl 폭/border-radius, td 패딩/폰트, 마지막 행 border) |

### 삭제 (1개 파일)
| 파일 | 삭제 사유 |
|---|---|
| `drf-server/static/js/dashboard/panels/gas-panel.js` | DOMContentLoaded에서 가스 KPI 스켈레톤을 "연결 중..." 텍스트로 즉시 덮어쓰는 핸들러 1개뿐. 전력 패널엔 동등 파일이 없고, 스켈레톤 ↔ 데이터 전환은 WS 수신부에서 처리하는 게 일관됨 |

## 4. API / 응답 / 인터페이스 변경

### Internal — WS 페이로드 의미 변경 (non-breaking semantically)

`/ws/sensors/`의 `total_power_kw` / `power_change_pct`가 stale 상태에서:
- Before: 하드코드 더미값(예: `1260` / `0.0`)
- After: `null`

프론트는 동시에 `!= null` 가드로 갱신 받으므로 외부 영향 없음. 외부에서 `/ws/sensors/`를 직접 구독하는 도구가 있다면 stale 시 키 값을 null로 처리하도록 보강 필요(현재 사용처 없음).

### 그 외
신규 엔드포인트·응답 키·파라미터 변경 없음.

## 5. 환경변수·설정 변경

해당 없음.

## 6. 마이그레이션 가이드

```bash
git pull

# 의존성 / DB / env 변경 없음
# 정적 자산 갱신만 발생 — 브라우저 캐시 강제 새로고침(Ctrl+F5) 권장

# 양 서버 재시작 (코드 변경 반영)
# 1) drf-server
cd drf-server && uv run manage.py runserver
# 2) fastapi-server
cd ../fastapi-server && uv run uvicorn app:app --reload --port 8001
```

## 7. 결정 근거 (ADR)

| 결정 | 채택안 | 검토했던 대안 | 근거 |
|---|---|---|---|
| 어드민 사이드바 폭 | **240px 드로어 + 풀라벨** | 70px 아이콘만 슬라이드 / 클릭 시 호버 expand | 한글 라벨이 잘려 가독성이 가장 큰 문제. 드로어 패턴은 메인 대쉬보드와 일관. |
| AdminSNB 토글 위치 | **`admin/main.js`에 ~10줄 인라인** | `shared/snb-toggle.js` 추출 / `layout.js` 재사용 | 어드민은 menu_tree API 호출·헤더 시계가 불필요. 공유 추상은 과한 설계. |
| 어드민 로고 위치 | **토픽바 좌측 (햄버거 옆)** | 사이드바 내 유지 | 드로어 기본 닫힘이라 사이드바 안의 로고는 안 보임. 대쉬보드 패턴과 일관. |
| 로고 이미지 사이즈 | **`height:30px; width:auto`** | 정사각 32x32 / 가변 컨테이너 비율 보존 | 헤더 높이(52px)/토픽바(60px) 안에 자연스럽게 들어가는 30px가 시각 균형 좋음. width auto로 종횡비 유지. |
| 로그인 뱃지 텍스트 | **"산재 예방 통합 관제 플랫폼" + 외부 `.system-name` 제거** | "로고" 텍스트 유지 / 외부 텍스트 유지 | 자리표시 "로고"는 의미 없음. 뱃지 안과 외부에 같은 문구가 중복돼 외부 제거. |
| 클래스 네임스페이스 | **`admin-snb-drawer` / `admin-snb-overlay`** | 대쉬보드 `.snb-drawer`/`.snb-overlay` 재사용 | `header.css`가 어드민에 우연히 로드돼도 충돌 회피. 어드민 토픽바 60px ↔ 대쉬보드 헤더 52px라 `top` 값도 다름. |
| `gas-panel.js` 처리 | **파일 삭제 + main.html 스크립트 태그 제거** | 본문 비우기 / 주석 처리 | 역할이 사라진 파일을 남기면 의도 불명. 전력 패널엔 동등 파일이 없어 비대칭. |
| stale 시 backend 응답 | **`null` 송신** | 하드코드 더미값 유지 / 키 자체 미포함 | 더미 미가동 시에도 KPI에 가짜 숫자가 표시되는 게 운영자 혼란. 키 미포함은 프론트 측 분기 추가 부담 — null이 가장 깔끔. |
| 프론트 null/undefined 가드 | **`!= null`** (loose) | `=== undefined && !== null` 분리 | 둘 다 차단 의도라 loose 비교가 가독성 좋음. JS 표준 idiom. |
| 가스 테이블 스타일 | **`#powerPanel`/`#gasPanel` 콤마 묶음** | `.tbl` 기본 룰을 통째로 격상 / 공통 클래스(`.panel-tbl`) 도입 | `.tbl`은 `checklist-tbl` 등 다른 곳도 사용. 공통 클래스 도입은 마크업 변경 동반(scope 확장). 셀렉터 묶음이 가장 surgical. |
| 차트 단위 전환 | **`applyPowerChartUnit(unit)` 분리 + `_switchPowerChart`에서 호출** | 차트 인스턴스 2개 분리(전체용/채널용) | 인스턴스 분리는 canvas 2개·메모리 2배. Y축 옵션·annotation·라벨만 교체하면 충분. |
| KW 임계치 상수값 | **WARNING 35 / DANGER 46** | 단순 W 임계치 × 1000 / 16배 환산 | 16채널 동시 가정 (16 × 2200=35.2, 16 × 2860=45.76)으로 상한선 결정. 운영 측정으로 추후 조정 가능. |
| WARNING 5초 → 10초 | **10초 채택** | 8초 / 15초 / env화 | 5초는 작업자 인지·이동 시간 부족(현장 피드백). env화는 배포 변경 부담 — 코드 상수로 충분. |
| 헤더 인사말 표현 | **"환영합니다" 한 가지 톤** | "안녕하세요" / 시간대별 분기 | 직설적·중립. 시간대 분기는 추가 복잡도 대비 가치 미미. |

## 8. 검증 방법 / 결과

### 자동 검증
JS/CSS/템플릿/Python 1줄 변경뿐이라 별도 자동 테스트 변경 없음. 기존 lint/pre-commit (ruff·ruff-format)는 영향 받는 .py 파일(`tasks.py`, `broadcast.py`)만 검사 — pass 확인.

### 수동 검증 체크리스트

**어드민 사이드바**
- [x] `/admin-panel/accounts-management/` 첫 로드 — 사이드바 닫힘, 토픽바 좌측에 햄버거+로고+타이틀
- [x] 햄버거 클릭 — 240px 드로어 슬라이드 인 + 백드롭
- [x] 백드롭 클릭 — 닫힘
- [x] 모든 링크 한글 라벨 가독 (잘림 없음)
- [x] 9개 어드민 페이지 모두 동일 동작 (base.html 상속)
- [x] `active_nav` 컨텍스트로 활성 링크 스타일 정상

**로고**
- [x] `/dashboard/` 헤더 — 텍스트 "LOGO" 사라지고 이미지 표시
- [x] `/admin-panel/...` 토픽바 — 햄버거 옆에 로고 이미지
- [x] `/accounts/login/` — 뱃지 안에 로고 + "산재 예방 통합 관제 플랫폼"
- [x] DevTools Network — `/static/img/logo.jpg` 200

**스켈레톤 일관화**
- [x] 페이지 로드 직후 가스 KPI/테이블이 스켈레톤 펄스 상태로 표시 (예전엔 즉시 텍스트)
- [x] WS 연결 전(`gas_loading: true`) 가스 패널이 스켈레톤 유지 (예전엔 "데이터 없음" 메시지)
- [x] 더미 미가동·실데이터 미수신 상태에서 전력 KPI가 "공백"/스켈레톤 (예전엔 가짜 ~1200kW)
- [x] 가스 첫 데이터 수신 시 스켈레톤 → 실데이터 전환 자연스러움

**가스 테이블 시각**
- [x] 가스 테이블 thead가 sticky로 스크롤 시 고정
- [x] 셀 padding/font가 전력 테이블과 동일

**헤더 인사말**
- [x] 로그인 후 헤더에 "{username}님 환영합니다" 표시

**전력 차트**
- [x] AI 예측 — 스마트 전력 위험 차트 idx 0("전체 사용량") Y축이 0~80 kW, 임계치 35/46
- [x] 화살표로 채널 이동 시 Y축이 W 단위(2200/2860 임계치)로 자동 전환
- [x] 라벨이 "예상 최대 부하 (kW)" ↔ "(W)" 동기화

**알람**
- [x] 가스/전력 알람 발생 후 WARNING이 10초 카운트다운 후 escalate (이전 5초)

### 검증 미완 (운영 회귀 시점)
- [ ] 어드민 모바일/태블릿 뷰포트에서 드로어 토글
- [ ] 다중 사용자 동시 접속에서 인사말 외 인터랙션 정상
- [ ] WS 단절 → stale → null KPI → 재연결 → 실데이터 회귀 시퀀스
- [ ] 16채널 풀가동 환경에서 KW 임계치 적정성 (필요 시 상수 재조정)

## 9. 하위 호환성 / 롤백

### Breaking 영역
없음. WS 페이로드의 stale 시 `null`은 문서화된 의미 변경이지만 외부 사용처가 현재 없음.

### Non-breaking 영역
- 외부 REST API 응답 / DB 스키마 / env 모두 동일
- 어드민 9개 페이지 자동 상속 (별도 마이그레이션 불필요)
- 더미 스크립트 송출 형식 동일

### 롤백
- 3개 커밋을 역순으로 revert: `git revert ea45b1b e74bd49 ec217a3` (또는 단일씩)
- 의존성·DB·env 변경 없음. 정적 자산 `logo.jpg`는 revert 시 자동 삭제

## 10. 후속 작업 / 참고

### 본 작업에서 의도적으로 미룬 것
- **헤더/토픽바 height 통일** — 대쉬보드 헤더 52px, 어드민 토픽바 60px가 그대로. 드로어 `top` 값 분기 유지. 통일 시 두 페이지 시각 일관성↑이지만 surgical 범위 외.
- **로그인 뱃지 디자인 정리** — 현재 30px 박스에 정사각 logo + 라벨. 로고 자체가 정사각이라 fit:cover로 박스 채움. 디자인 의도에 따라 contain·object-position 추가 조정 가능.
- **차트 가독성 개선** — 12시간 예측 vs 실시간 추이 시간축, 색상 콜드/웜 분리, 그리드 라인. 별도 작업.
- **알람 카운트다운 env화** — `WARNING_DURATION_SEC` 상수. 운영 환경별 조정 필요해지면 settings 필드로 승격.
- **`gas-panel.js` 책임 회수처** — 이전엔 KPI 초기 텍스트 표시 역할. 현재 WS 첫 수신 직전에 보일 fallback이 필요해지면 dashboard.css의 스켈레톤 펄스로 충분. 추가 안내 텍스트가 필요하면 `gas_loading` 분기에 `panel-msg` 활용 가능.
- **로고 자산 최적화** — 400x400 JPG(10.7 KB). 화면 30px로 축소 표시이므로 더 작게 리사이즈 + WebP 변환 가능 (성능 영향 미미라 보류).

### 관련 문서
- 동일 시기 별건 기록: `docs/changelog/realtime_map_dynamic_geofence.md` (commit `4248d8c`)
- 기존 변경 기록: `docs/changelog/phase{1,2,3,4,5}_*.md`
- 마스터 검증 체크리스트: `docs/changelog/00_pr_verification_checklist.md`
- 변경기록 작성 프롬프트: `skill/system_instruction_changelog.md`
