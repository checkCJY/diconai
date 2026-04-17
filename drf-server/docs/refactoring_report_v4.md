# 리팩토링 보고서 v4 — dashboard.js 모듈 분리

> 작성일: 2026-04-17
> 브랜치: `feature/mn-04.v1`
> 기준 문서: `docs/refactoring_report_v3.md` (util.js · alarm_popup.html · header.css 분리)

---

## 1. 요약 (Summary)

v3 이후에도 `dashboard.js` 가 825줄의 단일 파일로 남아 있었습니다.
팀원 수가 늘어남에 따라 **같은 파일에서 동시에 작업하는 상황이 빈번**해졌고, git 충돌 범위가 불필요하게 넓어지는 문제가 발생했습니다.

이번 v4 작업에서는 **코드 변경 없이** `dashboard.js` 를 기능 단위 9개 파일로 분리했습니다.

---

## 2. 분리 사유 (Key Reasons)

### 사유 1 — git 충돌 범위 최소화
단일 파일에 Auth / 레이아웃 / 지도 / 차트 / WebSocket / 알람 등이 모두 포함되어 있어
한 팀원의 변경이 다른 팀원이 수정 중인 코드와 충돌을 일으킬 가능성이 높았습니다.
모듈 단위로 파일을 분리하면 각자 담당 파일만 건드리므로 충돌 범위가 파일 단위로 좁혀집니다.

### 사유 2 — 유지보수 단위 명확화
"지도 버그 수정"을 위해 825줄짜리 파일 전체를 파악하는 것과,
`map-panel.js` 하나만 열어서 수정하는 것은 인지 부하가 전혀 다릅니다.
기능별 파일 분리는 변경 범위와 영향 범위를 직관적으로 드러냅니다.

### 사유 3 — 담당자 책임 분리
각 파일이 팀원 개인의 담당 기능과 1:1 로 대응되어, 코드 리뷰·히스토리 추적이 쉬워집니다.

---

## 3. 파일별 역할 (File Roles)

| 파일 | 역할 | 원본 위치 (dashboard.js) |
|------|------|--------------------------|
| `util.js` | 공통 유틸 (`pad`, `nowLabel`, `pushData`, `MAX_POINTS`, `levelLabel`) | v3에서 분리 완료 |
| `auth.js` | JWT 토큰 관리, API fetch 래퍼, 로그인 리다이렉트 (`Auth` 객체) | line 17–51 |
| `layout.js` | SNB 토글 (`SNB`), 메뉴 렌더링·아코디언 (`Menu`), 헤더 버튼·시계·로그아웃 (`Header`) | line 57–232 |
| `map-panel.js` | Leaflet 지도 초기화, 더미 데이터, 마커·지오펜스 렌더, 작업자 애니메이션, WS 연동 (`MapPanel`) | line 240–420 |
| `gas-panel.js` | 유해가스 테이블 초기값 렌더링 (`GAS_INIT_DATA` + `renderGasTable` IIFE) | line 426–447 |
| `charts.js` | Chart.js 가스·전력 차트 생성·업데이트, Y축 스케일 컨트롤 | line 455–522 |
| `websocket.js` | FastAPI WS 연결·재연결, 패널 12–15 실시간 DOM 업데이트, 차트·맵·알람 연동 | line 532–636 |
| `alarm-popup.js` | 위험 알림 팝업 큐·표시·자동닫힘 (`AlarmPopup`) | line 644–691 |
| `worker-panel.js` | 작업자 현황 패널 — admin/worker 뷰 분기, 폴링 API 호출 (`initMN04` IIFE) | line 699–796 |
| `app.js` | 앱 초기화 진입점 (`initApp` 함수 정의 + 호출) | line 802–825 |

---

## 4. 로드 순서 및 의존 관계 (Load Order)

```
[브라우저 HTML 파싱 — main_dashboard.html]

① util.js          ← 전역 선언: pad / nowLabel / pushData / MAX_POINTS / levelLabel
                      ※ 모든 파일이 이 심볼을 참조하므로 반드시 가장 먼저 로드

② auth.js          ← 의존: 없음
   alarm-popup.js  ← 의존: alarm_popup.html DOM
   gas-panel.js    ← 의존: util.js (levelLabel)
   charts.js       ← 의존: Chart.js CDN, util.js (MAX_POINTS / nowLabel / pushData)
   map-panel.js    ← 의존: Leaflet CDN, window.FACTORY_MAP_URL

③ layout.js        ← 의존: auth.js (Auth), util.js (pad / nowLabel)

④ worker-panel.js  ← 의존: 없음 (자체 fetch, DOMContentLoaded 대기)

⑤ websocket.js     ← 의존: charts.js (gasChart / powerChart)
                             map-panel.js (MapPanel)
                             alarm-popup.js (AlarmPopup)
                             util.js (levelLabel / nowLabel / pushData)

⑥ app.js           ← 의존: auth.js / layout.js / charts.js / map-panel.js
                             websocket.js / alarm-popup.js
                      ※ 모든 모듈이 정의된 후 마지막에 로드
```

### HTML 로드 선언 (main_dashboard.html 적용 내용)

```html
<script src="{% static 'js/util.js' %}"></script>
<script src="{% static 'js/auth.js' %}"></script>
<script src="{% static 'js/alarm-popup.js' %}"></script>
<script src="{% static 'js/gas-panel.js' %}"></script>
<script src="{% static 'js/charts.js' %}"></script>
<script src="{% static 'js/map-panel.js' %}"></script>
<script src="{% static 'js/layout.js' %}"></script>
<script src="{% static 'js/worker-panel.js' %}"></script>
<script src="{% static 'js/websocket.js' %}"></script>
<script src="{% static 'js/app.js' %}"></script>
```

---

## 5. 팀 작업 분리 기준 (Ownership Guide)

| 담당 기능 | 수정 파일 |
|-----------|-----------|
| 로그인·인증·토큰 | `auth.js` |
| SNB 사이드바·메뉴 | `layout.js` |
| 헤더 버튼·시계·로그아웃 | `layout.js` |
| Leaflet 지도·마커·지오펜스 | `map-panel.js` |
| 가스 테이블 초기값 | `gas-panel.js` |
| Chart.js 차트 생성·스케일 | `charts.js` |
| WebSocket 수신·패널 업데이트 | `websocket.js` |
| 알림 팝업 | `alarm-popup.js` + `templates/alarm_popup.html` |
| 작업자 현황 패널 (MN-04) | `worker-panel.js` |
| 앱 초기화 순서 변경 | `app.js` |
| 공통 유틸 추가·수정 | `util.js` |

---

## 6. 주의사항 (Important Notes)

### 주의 1 — dashboard.js 는 삭제하지 않음
`dashboard.js` 원본 파일은 참조용으로 남겨 두었습니다.
`main_dashboard.html` 에서 더 이상 로드하지 않으므로 브라우저에는 영향이 없습니다.
팀 내부 확인 후 필요 없다고 판단되면 별도 커밋으로 삭제하는 것을 권장합니다.

### 주의 2 — 로드 순서 변경 금지
`util.js` 를 첫 번째로 유지해야 합니다.
`app.js` 는 반드시 마지막에 위치해야 합니다.
`websocket.js` 는 `charts.js`, `map-panel.js`, `alarm-popup.js` 보다 뒤에 위치해야 합니다.

### 주의 3 — 전역 변수 의존 구조
현재 모든 파일이 `<script>` 태그 직접 로드 방식으로 전역 스코프를 공유합니다.
각 파일에 `'use strict'` 가 선언되어 있으나, `gasChart` / `powerChart` / `MapPanel` / `AlarmPopup` 등의 심볼은 전역 변수로 파일 간에 공유됩니다.
향후 ES Module (`type="module"`) 이나 번들러(Vite / webpack) 도입 시 `import / export` 로 명시적 의존을 선언하도록 전환을 권장합니다.

### 주의 4 — 다른 페이지에서 일부 모듈만 사용할 경우
`alarm-popup.js` 를 다른 페이지에서 재사용할 때는 반드시 `alarm_popup.html` DOM 도 함께 include 해야 팝업이 정상 동작합니다.
`layout.js` 를 다른 페이지에서 사용할 때는 `auth.js` 와 `util.js` 를 먼저 로드해야 합니다.

---

## 7. 테스트 방법 (Test Plan)

### 서버 실행
```bash
# Django 서버
cd drf-server && python manage.py runserver

# FastAPI 서버 (WebSocket 테스트 시)
cd fastapi-server && uvicorn websocket:app --port 8001 --reload
```

### 체크리스트

#### 분리 후 기본 동작 확인
- [ ] 브라우저 콘솔에 `ReferenceError` 가 없는지 확인
- [ ] 헤더 우측 시계(HH:MM:SS)가 1초마다 정상 갱신되는지 확인
- [ ] 햄버거 클릭 시 SNB Drawer 열림/닫힘 확인
- [ ] 로그아웃 버튼 → 모달 표시 → 확인/취소 동작 확인

#### 지도 패널 (map-panel.js)
- [ ] Leaflet 지도가 공장 SVG 배경과 함께 정상 렌더되는지 확인
- [ ] 지도 탭(전체/작업자/위험구역/유해가스 센서/설비) 필터링 정상 동작 확인
- [ ] 작업자 마커가 1초 간격으로 이동하는지 확인

#### 차트 (charts.js)
- [ ] 패널 13, 15 차트가 초기 빈 상태로 렌더되는지 확인
- [ ] Y축 +/−/↺ 버튼이 정상 동작하는지 확인

#### 가스 테이블 (gas-panel.js)
- [ ] 페이지 로드 시 패널 12 테이블에 더미 9행이 표시되는지 확인
- [ ] `levelLabel` 기반 위험/주의/정상 텍스트가 정상 표시되는지 확인

#### WebSocket (websocket.js)
- [ ] wsStatus 배지가 "● 실시간 연결"로 전환되는지 확인
- [ ] 패널 12 테이블이 WS 수신 후 실시간 업데이트되는지 확인
- [ ] 패널 13, 15 차트가 실시간으로 데이터를 추가하는지 확인
- [ ] WS 연결 종료 후 5초 내 자동 재연결되는지 확인

#### 알림 팝업 (alarm-popup.js)
- [ ] `level === '위험'` 수신 시 팝업이 우측 상단에 표시되는지 확인
- [ ] ✕ 버튼 / 확인 버튼 클릭 시 팝업 닫힘 확인
- [ ] 10초 자동 닫힘 확인

#### 작업자 현황 패널 (worker-panel.js)
- [ ] `user_type === 'admin'` 이면 D View(KPI 카드) 표시 확인
- [ ] `user_type !== 'admin'` 이면 B View(상태 바) 표시 확인
- [ ] 30초마다 폴링 API 호출이 발생하는지 확인

---

## 8. 변경사항 비교 (Before / After)

| 구분 | v3 | v4 |
|------|----|----|
| JS 파일 수 | 2개 (`util.js` + `dashboard.js`) | **10개** (`util.js` + 분리된 9개 모듈) |
| `dashboard.js` 줄 수 | 825줄 | 비활성 (로드 제거, 파일은 유지) |
| 가장 큰 단일 JS 파일 | 825줄 (`dashboard.js`) | 약 175줄 (`map-panel.js`) |
| 팀원 충돌 범위 | 파일 전체 (825줄) | 담당 모듈 파일 (~30–175줄) |
| HTML 스크립트 태그 수 | 2개 | **10개** |
