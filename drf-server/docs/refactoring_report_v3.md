# 리팩토링 보고서 v3 — 파일 분리 작업

> 작성일: 2026-04-16
> 브랜치: `feature/mn-04.v1`
> 기준 문서: `docs/refactoring_report_v2.md` (v2 버그 수정)

---

## 1. 요약 (Summary)

**통합 대시보드 코드 3파일(HTML·CSS·JS)이 각 800~900줄 수준으로 비대해짐에 따라, 역할 단위로 파일을 분리하여 유지보수 가독성과 재사용성을 개선.**

- `dashboard.js` 내 3곳에서 중복 선언된 `pad()` 함수, 2곳에서 중복된 `levelLabel` 상수 등 공통 유틸을 `util.js`로 추출
- `main_dashboard.html` 인라인 알림 팝업 블록을 `alarm_popup.html` 컴포넌트로 분리
- `dashboard.css` 헤더/SNB/모달 관련 스타일을 `header.css`로 분리 — `header.html`과 CSS를 쌍으로 관리

---

## 2. 주요 분리 사유 (Key Reasons)

### 사유 1 — `pad()` 함수 3중 중복
```
Header.initClock()       → const pad = n => String(n).padStart(2, '0');  // 158번째 줄
Header.updateLastUpdated() → const pad = n => String(n).padStart(2, '0');  // 169번째 줄
nowLabel()               → const d = new Date(), pad = n => ...            // 458번째 줄
```
동일한 로직이 3곳에 국소 선언되어 있어, 한 곳을 수정해도 나머지가 반영되지 않는 위험 존재.

### 사유 2 — `levelLabel` 상수 2중 중복
```
renderGasTable (line 437) → const levelLabel = { danger: '위험', caution: '주의', safe: '정상' };
WebSocket onmessage (line 611) → levelLabel[eq.level]  ← 동일 객체를 참조
```
상수가 한 곳에 선언되고 다른 곳에서 암묵적으로 의존하는 구조. `levelLabel`을 선언한 위치 위에서 WebSocket 코드가 실행될 경우 `undefined` 오류 발생 가능.

### 사유 3 — `alarm-popup` HTML이 `main_dashboard.html` 본문에 직접 포함
알림 팝업은 독립 UI 컴포넌트임에도 본문 하단에 인라인으로 작성되어 있어, 다른 페이지에서 재사용 불가. 별도 include 파일로 분리 시 재사용 및 단독 수정이 용이.

### 사유 4 — 헤더 관련 CSS가 대시보드 CSS와 혼재
`header.html`이 독립 컴포넌트로 분리되었음에도, 해당 컴포넌트의 스타일이 `dashboard.css`에 남아 있어 "HTML 파일 ↔ CSS 파일" 간 대응 관계가 불명확.

---

## 3. 파일별 역할 (File Roles)

| 파일 | 역할 | 비고 |
|------|------|------|
| `static/js/util.js` | 공통 유틸 상수·함수 (`pad`, `nowLabel`, `pushData`, `MAX_POINTS`, `levelLabel`) | `dashboard.js` 보다 **먼저** 로드 필수 |
| `static/js/dashboard.js` | 대시보드 핵심 모듈 (Auth·SNB·Menu·Header·MapPanel·Charts·WebSocket·AlarmPopup·MN-04·initApp) | `util.js` 의존 |
| `templates/alarm_popup.html` | CM-07 실시간 알림 팝업 DOM 컴포넌트 | `main_dashboard.html` 에서 `{% include %}` |
| `templates/header.html` | SNB 오버레이·Drawer·헤더·로그아웃 모달 DOM 컴포넌트 | 기존 분리 유지 |
| `templates/main_dashboard.html` | 대시보드 페이지 진입점 (레이아웃 + include 조합) | CSS/JS 로딩 순서 관리 |
| `static/css/header.css` | 헤더·SNB·로그아웃 모달·스피너 스타일 | `header.html` 과 쌍으로 관리 |
| `static/css/dashboard.css` | 리셋·변수·레이아웃·패널·맵·차트·알람팝업 스타일 | CSS 변수(`:root`) 보유 → **먼저** 로드 필수 |

---

## 4. 데이터 흐름 (Data Flow)

### JS 로딩 순서 및 의존 관계

```
[브라우저 HTML 파싱]
    ⬇
<script src="util.js">           ← ① 전역 선언: pad / nowLabel / pushData / MAX_POINTS / levelLabel
    ⬇
<script src="dashboard.js">      ← ② util.js 의 전역 심볼을 그대로 참조
    │
    ├── Auth         (JWT 관리)
    ├── SNB          (사이드 내비게이션)
    ├── Menu         (메뉴 렌더링·아코디언)
    ├── Header       (시계·새로고침·홈·관리자·로그아웃)
    │     └── initClock()        → pad  [util.js]
    │     └── updateLastUpdated() → nowLabel()  [util.js]
    ├── MapPanel     (Leaflet 실시간 맵)
    ├── renderGasTable()          → levelLabel  [util.js]
    ├── initCharts() + pushData() → MAX_POINTS / nowLabel / pushData  [util.js]
    ├── initWebSocket()           → levelLabel / pushData / nowLabel  [util.js]
    ├── AlarmPopup   (위험 팝업 큐)
    ├── initMN04()   (작업자 현황 패널)
    └── initApp()    (앱 초기화 진입점)
```

### CSS 로딩 순서 및 의존 관계

```
<link href="dashboard.css">   ← ① :root 변수 정의 (--bg, --danger, --blue 등)
    ⬇
<link href="header.css">      ← ② var(--bg2), var(--danger) 등 dashboard.css 변수 참조
```

### HTML include 구조

```
main_dashboard.html
    ├── {% include 'header.html' %}       ← SNB Overlay + SNB Drawer + Header + 로그아웃 모달
    ├── <div class="body-wrap">           ← 대시보드 패널 본문 (패널 8~15)
    └── {% include 'alarm_popup.html' %}  ← CM-07 알림 팝업 (신규 분리)
```

---

## 5. 테스트 방법 (Test Plan)

### 기본 동작 확인
```bash
# Django 서버 실행
cd drf-server && python manage.py runserver

# FastAPI 서버 실행 (WebSocket 테스트 시)
cd fastapi-server && uvicorn websocket:app --port 8001 --reload
```

### 체크리스트

#### util.js 분리 검증
- [ ] 브라우저 콘솔에서 `pad(9)` 입력 시 `"09"` 반환 확인
- [ ] 브라우저 콘솔에서 `nowLabel()` 입력 시 `"HH:MM:SS"` 형식 반환 확인
- [ ] 브라우저 콘솔에서 `MAX_POINTS` 입력 시 `30` 반환 확인
- [ ] 브라우저 콘솔에서 `levelLabel` 입력 시 `{danger: '위험', caution: '주의', safe: '정상'}` 반환 확인
- [ ] 헤더 우측 시계(HH:MM:SS)가 정상 갱신되는지 확인 (pad 전역 사용)
- [ ] "최종 갱신" 시각이 새로고침 버튼 클릭 시 nowLabel() 로 정상 갱신되는지 확인

#### alarm_popup.html 분리 검증
- [ ] `http://localhost:8000/` 접속 후 위험 알람 팝업이 화면 우측 상단에 정상 표시되는지 확인
- [ ] ✕ 버튼 / 확인 버튼으로 팝업 닫힘 확인
- [ ] 10초 자동 닫힘 확인

#### header.css 분리 검증
- [ ] 햄버거 버튼 클릭 시 SNB Drawer가 정상 열리고 닫히는지 확인
- [ ] 로그아웃 버튼 클릭 시 모달이 맵 위에 정상 표시되는지 확인
- [ ] 새로고침 버튼 클릭 시 스피너 애니메이션 정상 동작 확인
- [ ] 관리자 메뉴 버튼이 admin/superadmin 계정에서만 노출되는지 확인

#### 가스·전력 테이블 levelLabel 검증
- [ ] WebSocket 연결 후 유해가스 테이블에 "위험/주의/정상" 레이블이 정상 표시되는지 확인
- [ ] 전력 장비 테이블에 "위험/주의/정상" 레이블이 정상 표시되는지 확인

#### 차트 동작 검증
- [ ] 패널 13 (AI 예측 가스) 실시간 라인 차트가 WebSocket 수신 시 업데이트되는지 확인
- [ ] 패널 15 (AI 예측 전력) 실시간 라인 차트가 WebSocket 수신 시 업데이트되는지 확인
- [ ] Y축 +/−/↺ 버튼이 정상 동작하는지 확인

---

## 6. 그 외 검토 사항 (Additional Review)

### 검토 1 — `dashboard.js` 추가 분리 가능 단위
현재 `dashboard.js` 는 약 820줄로 여전히 큽니다. 향후 기능이 추가될 경우 아래 단위로 분리를 고려할 수 있습니다.

| 대상 모듈 | 예상 분리 파일 | 우선순위 |
|-----------|---------------|---------|
| `Auth` | `auth.js` | 중 — 로그인 페이지 등 다른 곳에서도 사용 가능성 있음 |
| `MapPanel` | `map.js` | 중 — Leaflet 의존 코드가 집중되어 있음 |
| `AlarmPopup` | `alarm.js` | 낮음 — `alarm_popup.html` 과 세트로 관리 가능 |
| `initMN04` | `mn04.js` | 낮음 — 다른 페이지에서 재사용 시 분리 가치 있음 |

### 검토 2 — 알람 팝업 UX 개선 검토
v2 보고서에서 언급된 것처럼 현재 알람 팝업은 큐(Queue) 방식으로 순서대로 하나씩 표시됩니다.
연속 위험 발생 시 팝업이 쌓이지 않고 대기열에 쌓이는 방식이므로, 운영 환경에서는 최신 위험을 즉시 인지하기 어려울 수 있습니다.
→ **스택(Stack) 누적 방식** 또는 **배지(Badge) 카운트 방식**으로 전환을 검토 권장.

### 검토 3 — CSS 변수 의존 순서
`header.css`의 모든 선택자가 `dashboard.css`의 `:root` 변수(`--bg2`, `--danger` 등)를 참조합니다.
`header.css`를 `dashboard.css`보다 먼저 로드하면 변수가 `undefined`가 되어 스타일이 깨집니다.
`main_dashboard.html` 외 다른 페이지에서 `header.html`을 include할 경우, 해당 페이지에도 반드시 `dashboard.css → header.css` 순서로 로드해야 합니다.

### 검토 4 — 더미 데이터 분리 검토
`MapPanel` 내 `DUMMY_GAS_SENSORS`, `DUMMY_POWER_DEVICES`, `DUMMY_GEOFENCES`, `DUMMY_WORKERS` 4개의 더미 데이터 배열이 `dashboard.js` 내부에 하드코딩되어 있습니다.
실제 API 연동 전환 시 이 부분을 별도 `dummy_data.js` 혹은 백엔드 fixture로 이전하면 깔끔합니다.

---

## 7. 변경사항 비교 (Before / After)

### 파일 구조 변화

| 구분 | v2 (버그 수정 후) | v3 (파일 분리 후) |
|------|-----------------|-----------------|
| HTML | `main_dashboard.html` (243줄) + `header.html` | `main_dashboard.html` (235줄) + `header.html` + **`alarm_popup.html`** (신규) |
| CSS | `dashboard.css` (320줄) | `dashboard.css` (191줄) + **`header.css`** (신규, 129줄) |
| JS | `dashboard.js` (841줄) | `dashboard.js` (815줄) + **`util.js`** (신규, 44줄) |

### 코드 변화 요약

| 항목 | v2 | v3 |
|------|----|----|
| `pad()` 선언 | 3곳 중복 (local) | **1곳** (`util.js` 전역) |
| `levelLabel` 선언 | 2곳 혼재 (선언+암묵적 참조) | **1곳** (`util.js` 전역) |
| `MAX_POINTS` / `nowLabel` / `pushData` | `dashboard.js` 내부 | **`util.js`** 로 이동 |
| 알람 팝업 HTML | `main_dashboard.html` 인라인 | **`alarm_popup.html`** 컴포넌트 |
| 헤더 관련 CSS | `dashboard.css` 혼재 (320줄) | **`header.css`** 분리 (129줄) |
| `Header.updateLastUpdated()` | `const pad = ...` + 수동 포맷 | `nowLabel()` 호출로 단순화 |
| CSS 로딩 | `dashboard.css` 1개 | `dashboard.css` → `header.css` 순서로 2개 |
| JS 로딩 | `dashboard.js` 1개 | `util.js` → `dashboard.js` 순서로 2개 |
