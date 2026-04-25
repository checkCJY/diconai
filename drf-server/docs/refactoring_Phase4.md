# Phase 4 리팩토링 — DRF 서버 개발자 분기 파일 통합 및 디렉토리 재구조화

## 개요

Phase 3까지 FastAPI 서버 구조를 정리했다면, Phase 4에서는 DRF 서버(프론트엔드 + 뷰)를 대상으로
개발자별(`_CJY`, `_jhh`)로 분기되어 있던 파일들을 하나의 통합 파일로 병합했다.
이후 유지보수성 강화를 위해 `templates/`와 `static/js/` 디렉토리를 역할 기준으로 재분류했다.
마지막으로 모든 JS·HTML 파일에 기존 스타일에 맞는 주석을 추가했다.

---

## 변경 전 구조

```
drf-server/
├── templates/
│   ├── main_dashboard.html          # 기존 대시보드 (미연결 상태)
│   ├── main_dashboard_CJY.html      # CJY 작업본 — 전력 패널 신버전
│   ├── main_dashboard_jhh.html      # jhh 작업본 — 가스 패널 중심
│   ├── components/
│   │   ├── header.html
│   │   └── alarm_popup.html
│   │   # alarm_panel.html          ← 고아 파일 (참조 없음, 존재하지 않는 JS 로드)
│   └── snb_details/                 # 상세 페이지 8개
├── static/
│   ├── css/
│   │   ├── dashboard.css
│   │   └── dashboard_CJY.css        # CJY 전력 패널 전용 스타일
│   └── js/
│       └── refactors/               # 역할이 혼재된 폴더명
│           ├── util.js
│           ├── auth.js
│           ├── layout.js
│           ├── alarm-popup.js
│           ├── app.js
│           ├── app-sub.js
│           ├── charts.js
│           ├── charts_CJY.js        # CJY 작업본 — 전력 임계치 annotation
│           ├── websocket.js
│           ├── websocket_CJY.js     # CJY 작업본 — 전력 실데이터 + AI 채널 네비
│           ├── websocket_jhh.js     # jhh 작업본 — 9종 가스 + 알람 배열 순회
│           ├── event-panel.js
│           ├── gas-panel.js
│           ├── gas-panel_jhh.js     # gas-panel.js와 내용 동일한 중복 파일
│           ├── map-panel.js
│           └── worker-panel.js
└── apps/dashboard/
    ├── views.py                     # main_dashboard_CJY.html 서빙, jhh 뷰 별도 존재
    └── urls.py                      # /jhh/ 경로 존재
```

### 구조의 문제점

| 문제 | 설명 |
|------|------|
| 개발자 분기 파일 | `_CJY`, `_jhh` 접미사 파일이 병렬 존재, 어느 것이 실제 서비스인지 불명확 |
| 고아 파일 | `alarm_panel.html` — 존재하지 않는 `css/style.css`, `js/main.js`를 로드 |
| 중복 파일 | `gas-panel_jhh.js` — `gas-panel.js`와 내용 동일 |
| 폴더명 불명확 | `refactors/` — 임시 폴더처럼 보이고 역할이 혼재 |
| 단일 파일 과밀 | `main_dashboard.html` 260줄, 5개 패널이 모두 한 파일에 집중 |

---

## 변경 후 구조

```
drf-server/
├── templates/
│   ├── dashboard/
│   │   ├── main.html                # 메인 대시보드 — includes만 남긴 씬(thin) 파일
│   │   └── panels/
│   │       ├── safety_panel.html    # 나의 안전확인 + 작업자 현황 (col-left)
│   │       ├── map_panel.html       # 실시간 모니터링 지도 (col-mid)
│   │       ├── event_panel.html     # 이벤트 현황 (col-right)
│   │       ├── gas_panel.html       # 유해가스 현황 + AI 예측 가스 (bottom)
│   │       └── power_panel.html     # 전력 현황 + AI 예측 전력 (bottom)
│   ├── components/
│   │   ├── header.html
│   │   ├── alarm_popup.html
│   │   └── geofence_modal.html      # 지오펜스 저장 모달 (main.html에서 분리)
│   ├── snb_details/                 # 상세 페이지 8개 (변경 없음)
│   ├── admin/
│   └── auth/
├── static/
│   ├── css/
│   │   └── dashboard.css            # dashboard_CJY.css 병합 완료
│   └── js/
│       ├── shared/                  # 여러 페이지 공통 모듈
│       │   ├── util.js
│       │   ├── auth.js
│       │   ├── layout.js
│       │   ├── alarm-popup.js
│       │   └── app-sub.js
│       ├── dashboard/               # 메인 대시보드 전용 모듈
│       │   ├── app.js
│       │   ├── websocket.js
│       │   ├── charts.js
│       │   └── panels/
│       │       ├── event-panel.js
│       │       ├── gas-panel.js
│       │       ├── map-panel.js
│       │       └── worker-panel.js
│       ├── detail/                  # monitoring/power 상세 페이지 전용 (변경 없음)
│       │   ├── power_system.js
│       │   ├── websocket_power.js
│       │   └── ui-exception.js
│       └── admin/                   # 관리자 페이지 전용 (변경 없음)
└── apps/dashboard/
    ├── views.py                     # main_dashboard() → dashboard/main.html 서빙
    └── urls.py                      # /jhh/ 경로 제거
```

---

## 핵심 변경 내용

### 1. 개발자 분기 파일 병합

3개 파일(원본·CJY·jhh)에 흩어진 기능을 각 개발자의 기여가 동등하게 반영된 하나의 파일로 통합했다.
병합 원칙: **최적 기능 선택** — 서비스 중인 파일이 기본값이 아니라, 기능의 완성도 기준으로 선택했다.

#### websocket.js 병합 내용

| 기능 | 출처 |
|------|------|
| 9종 가스 GAS_META + `{gas}_risk` 서버 측 위험도 | jhh |
| `data.alarms[]` 배열 순회 알람 처리 | jhh |
| `Object.entries(data.worker_positions)` 위치 파싱 | jhh |
| AI 전력 채널 네비게이션 (`_aiPowerPreds`, `_renderAIPowerNav`) | CJY |
| 채널별 히스토리 (`_pushChannelHistory`, `_switchPowerChart`) | CJY |
| W/V/A/ON-OFF/위험도 전력 테이블 컬럼 | CJY |
| `power_loading` 스켈레톤 보존 | CJY |
| `total_power_kw` / kW 단위 | 공통 (jhh 원본의 `total_power_mw` 오류 수정 포함) |

#### charts.js 병합 내용

| 기능 | 처리 |
|------|------|
| 전력 임계치 annotation (`_powerAnnotations`, `POWER_THRESHOLD_*`) | CJY 채택 |
| `updatePowerThresholds()` Phase B 스텁 | 유지 |
| 줌 버튼 관련 코드 (`adjustYScale`, `scaleState`, `initYScaleControls`) | **제거** |

#### main_dashboard.html 병합 내용

| 영역 | 채택 버전 |
|------|-----------|
| 전력 현황 패널 (설비 테이블) | CJY — W/V/A/ON-OFF/위험도 컬럼, 스켈레톤 행, `power-kpi-box` |
| AI 전력 예측 패널 | CJY — ◁▷ 실제 버튼, `ai-kpi-box`, `ai-nav-ctrl` |
| 줌 버튼 DOM (`chart-controls` div) | **제거** |

#### dashboard.css 병합 내용

`dashboard_CJY.css` 전체를 `dashboard.css` 하단에 병합했다.

| 추가된 스타일 |
|--------------|
| 스켈레톤 UI (`.skeleton`, `@keyframes skel-pulse`, `.skel-text`, `.skel-badge`) |
| 전력 KPI 박스 (`.power-kpi-box`, `.power-kpi-row`, `.power-total`) |
| AI 패널 (`.ai-kpi-box`, `.ai-nav-ctrl`, `.ai-nav-btn`, `.ai-kpi-divider`) |
| 전력 테이블 스크롤 (`.tbl-scroll`, sticky thead) |
| 위험도 행 색상 (`.risk-row.risk-danger`, `.risk-row.risk-caution`, `.risk-row.risk-safe`) |

---

### 2. templates/ 패널 분리

`dashboard/main.html`에 집중되어 있던 260줄의 HTML을 5개 패널 파일과 1개 컴포넌트로 분리했다.
분리 후 `main.html`은 `{% include %}` 선언만 남은 씬 파일이 된다.

```html
<!-- dashboard/main.html 분리 후 구조 -->
{% include 'components/header.html' %}
<div class="body-wrap">
  <div class="top-row">
    {% include 'dashboard/panels/safety_panel.html' %}
    {% include 'dashboard/panels/map_panel.html' %}
    {% include 'dashboard/panels/event_panel.html' %}
  </div>
  <div class="bottom-row">
    {% include 'dashboard/panels/gas_panel.html' %}
    {% include 'dashboard/panels/power_panel.html' %}
  </div>
</div>
{% include 'components/alarm_popup.html' %}
{% include 'components/geofence_modal.html' %}
```

---

### 3. static/js/ 디렉토리 재분류

`refactors/` 폴더를 역할 기준 3개 폴더로 재분류했다.

| 폴더 | 역할 | 포함 파일 |
|------|------|-----------|
| `shared/` | 여러 페이지 공통 | util, auth, layout, alarm-popup, app-sub |
| `dashboard/` | 메인 대시보드 전용 | app, websocket, charts |
| `dashboard/panels/` | 패널별 모듈 | event-panel, gas-panel, map-panel, worker-panel |

모든 `snb_details/`, `admin/` HTML 파일의 `js/refactors/` 경로를 `js/shared/`로 일괄 업데이트했다.

---

### 4. views.py / urls.py 정리

```python
# 변경 전
def main_dashboard(request):
    return render(request, "main_dashboard_CJY.html")

def main_dashboard_jhh(request):          # 삭제
    return render(request, "main_dashboard_jhh.html")

# 변경 후
def main_dashboard(request):
    return render(request, "dashboard/main.html")
```

```python
# urls.py — 제거된 경로
path("jhh/", views.main_dashboard_jhh, name="main-dashboard-jhh")  # 삭제
```

---

### 5. websocket_power.js 버그 수정

`monitoring/power/` 상세 페이지가 실제 데이터를 수신하지 못하던 포트 오류를 수정했다.

```js
// 변경 전
const WS_URL = 'ws://127.0.0.1:8002/ws/sensors/';

// 변경 후
const WS_URL = 'ws://127.0.0.1:8001/ws/sensors/';
```

---

### 6. 주석 추가 기준 및 적용 범위

#### 기준

| 대상 | 스타일 | 원칙 |
|------|--------|------|
| HTML | `<!-- ── 섹션명 ────── -->` | 패널/블록 단위에만 추가, 자명한 div는 생략 |
| JS 섹션 | `// ──────────────────────────────` | 기존 파일 내 섹션 블록 방식 유지 |
| JS 함수 | `// ── 설명 ──────────────────────` | 함수명만으로 역할이 불명확한 경우에만 추가 |

#### 적용 파일

| 파일 | 추가된 주석 대상 |
|------|----------------|
| `dashboard/app.js` | `loadMySafetyStatus` 섹션 |
| `shared/alarm-popup.js` | `_process` |
| `shared/layout.js` | `Menu.render`, `Header.handleRefresh`, `Header.handleHome`, `initHeaderAndSNB` 섹션 |
| `dashboard/panels/map-panel.js` | `riskColor`, `levelToStatus`, `init`, `_drawAll` |
| `dashboard/panels/worker-panel.js` | `renderWorkerStatus`, `renderAdminSummary`, `init` |
| `dashboard/panels/safety_panel.html` | 패널 구분, 작업자·관리자 뷰 분기 |

**주석 미적용 파일** (기존 주석 또는 함수명으로 충분):
`auth.js`, `util.js`, `ui-exception.js`, `websocket.js`, `charts.js`, `event-panel.js`

---

## 삭제된 파일 목록

| 파일 | 이유 |
|------|------|
| `templates/main_dashboard.html` | `templates/dashboard/main.html`로 이동 및 패널 분리 |
| `templates/main_dashboard_CJY.html` | `dashboard/main.html`로 통합 |
| `templates/main_dashboard_jhh.html` | 동일 |
| `templates/alarm_panel.html` | 고아 파일 — 참조 뷰 없음, 존재하지 않는 JS/CSS 로드 |
| `static/css/dashboard_CJY.css` | `dashboard.css` 하단에 병합 |
| `static/js/refactors/charts_CJY.js` | `dashboard/charts.js`로 통합 |
| `static/js/refactors/websocket_CJY.js` | `dashboard/websocket.js`로 통합 |
| `static/js/refactors/websocket_jhh.js` | 동일 |
| `static/js/refactors/gas-panel_jhh.js` | `dashboard/panels/gas-panel.js`와 내용 동일, 중복 제거 |
| `static/js/refactors/` (폴더 전체) | `shared/`, `dashboard/`, `dashboard/panels/`로 재분류 후 삭제 |

---

## 테스트 방법

### 서버 기동

```bash
# 터미널 1 — DRF 서버
cd drf-server
python manage.py runserver          # http://127.0.0.1:8000

# 터미널 2 — FastAPI 서버
cd fastapi-server
uvicorn app:app --reload --port 8001

# 터미널 3 — 더미 데이터 전송
cd fastapi-server
python -m dummies.gas_dummy         # 1초 주기
python -m dummies.power_dummy       # 3초 주기
```

### 브라우저 확인 체크리스트

| 항목 | 확인 위치 | 기대 동작 |
|------|-----------|-----------|
| WebSocket 연결 | `/dashboard/` 헤더 | `연결 중...` → `연결됨` |
| 가스 테이블 | 하단 패널 — 유해가스 현황 | 9종 가스 농도 + 위험도 배지 |
| AI 가스 차트 | 하단 패널 — AI 예측 가스 | 현재·예측 농도 라인 업데이트 |
| 전력 테이블 | 하단 패널 — 전력 현황 | 스켈레톤 → W/V/A/ON·OFF/위험도 |
| 전력 KPI | 전력 패널 상단 | `현재 전체 스마트 파워 전력 사용량` 숫자 |
| AI 전력 차트 | 하단 패널 — AI 예측 전력 | ◁▷ 버튼 채널 전환, 임계선 표시 |
| 알람 팝업 | 전체 페이지 | 10% 확률 위험값 발생 시 팝업 |
| 전력 상세 페이지 | `/dashboard/monitoring/power/` | 설비 카드 + 막대 그래프 렌더링 |

### DevTools 확인

```
Network → WS → /ws/sensors/ 프레임에서 아래 키 존재 여부 확인:
  co_risk, h2s_risk   ← 가스 위험도 (Phase 3 FastAPI)
  total_power_kw      ← 전력 총합
  equipment[]         ← 설비별 데이터
  alarms[]            ← 알람 이벤트
```
