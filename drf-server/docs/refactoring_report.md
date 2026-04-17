# 리팩토링 보고서 — 대시보드 통합

> 작성일: 2026-04-16
> 브랜치: `feature/mn-04.v1`

---

## 1. 요약 (Summary)

**분산된 3개의 개별 대시보드(dashboard_jh, dashboard_CJY, dashboard_sh)와 분리된 JS/CSS 파일들을 단일 `main_dashboard.html` + `dashboard.js` + `dashboard.css` 로 통합하여 코드 중복 제거 및 유지보수성 향상.**

---

## 2. 주요 변경 사항 (Key Changes)

### 프론트엔드 — HTML
- `dashboard_jh.html`, `dashboard_CJY.html`, `dashboard_sh.html` 3개 → `main_dashboard.html` 1개로 통합
- 인라인 헤더 코드 2곳(dashboard_CJY, dashboard_sh) → `{% include 'header.html' %}` 로 통일
- Leaflet 맵 SVG 경로(`{% static %}` 태그)를 `window.FACTORY_MAP_URL` 전역 변수로 주입하여 JS 파일 분리 가능하게 변경
- 인라인 `<style>` 블록 (Leaflet 팝업 스타일, ws-status 등) → `dashboard.css` 로 이전

### 프론트엔드 — JavaScript
| 파일 | 변경 내용 |
|------|-----------|
| `main.js` (551줄) | `dashboard.js` 로 흡수 |
| `main_jh.js` (551줄) | `main.js` 완전 중복 → `dashboard.js` 1개로 대체 |
| `CJY.js` (191줄) | `dashboard.js` 하단 `initMN04()` 섹션으로 병합 |
| `dashboard_sh.html` 인라인 JS (~230줄) | `dashboard.js` 의 `MapPanel` 객체로 추출 |
| **`dashboard.js` (신규, ~390줄)** | 위 4개 출처 통합 결과물 |

**WebSocket 버그 수정** (`main.js` → `dashboard.js`):
- 기존: `ws.onmessage` 핸들러 정의 누락, `statusDiv` 미정의 참조 오류
- 변경: `ws.onmessage = (e) => { ... }` 정상 래핑, 상태 표시를 `wsStatusEl`(DOM 요소) 방식으로 통일
- 재연결 로직: `ws.onclose` 에서 `setTimeout(connect, 5000)` 자동 재연결 추가

### 프론트엔드 — CSS
| 파일 | 변경 내용 |
|------|-----------|
| `style.css` (246줄) | `dashboard.css` 로 흡수 |
| `CJY.css` (131줄) | `dashboard.css` MN-04 섹션으로 병합 |
| `dashboard_sh.html` 인라인 `<style>` (~35줄) | `dashboard.css` (Leaflet/ws-status 섹션) 로 이전 |
| **`dashboard.css` (신규, ~280줄)** | 위 3개 출처 통합 결과물 |

### 백엔드 — urls.py
- 루트(`""`) → `dashboard_sh.html` 에서 `main_dashboard.html` 로 변경
- `/dashboard/` 경로 신규 추가 (동일 뷰)
- 기존 `/dashboard_jh/`, `/dashboard_sh/`, `/dashboard-cjy/` 경로는 **하위 호환용으로 유지**
- 뷰 함수명 정리: `dashboard()` → `main_dashboard()`, `dashboard_page()` → `dashboard_jh()`

---

## 3. 데이터 흐름도 (Data Flow)

### 3-A. 페이지 진입 흐름

```
[브라우저] URL: / 또는 /dashboard/ 접근
    ⬇
[config/urls.py]
    path("") or path("dashboard/") → main_dashboard(request)
    ⬇
[main_dashboard.html] 렌더링
    ├── {% include 'header.html' %}  → SNB Drawer + Header DOM
    ├── <link dashboard.css>         → 전체 스타일 로드
    ├── <script Chart.js CDN>
    ├── <script Leaflet.js CDN>
    ├── window.FACTORY_MAP_URL 주입  → {% static 'img/factory_map.svg' %}
    └── <script dashboard.js>        → initApp() 자동 실행
```

### 3-B. JS 초기화 흐름 (dashboard.js → initApp)

```
[dashboard.js] initApp() 호출
    ⬇
① [Auth.getAccessToken()]
    ┌──────────────────────────────────────┐
    │  토큰 없음 → Auth.redirectLogin()    │
    │  토큰 있음 → Auth.getMe() API 호출   │
    └──────────────────────────────────────┘
    ⬇ GET /api/auth/me/  (Bearer 헤더)
[apps/accounts/views.py → MeView]
    └── JWT 검증 → { username, role, menu_tree } 반환
    ⬇
② [Header.renderUser(username)]
    → #headerUsername 텍스트 갱신
    → role === 'admin'이면 #btnAdmin display:'' (노출)

③ [Menu.render(menu_tree)]
    → #snbMenu 에 depth1/depth2 아코디언 목록 DOM 생성

④ [SNB.init() / Header.init()]
    → #hamburger, #snbClose, #snbOverlay 이벤트 바인딩
    → 시계 setInterval(tick, 1000) 시작

⑤ [initCharts()]
    → Chart.js gasChart (#chartGas), powerChart (#chartPower) 인스턴스 생성
    → Y축 스케일 버튼 이벤트 바인딩

⑥ [MapPanel.init()]
    → L.map('#map', CRS.Simple) 초기화
    → L.imageOverlay(window.FACTORY_MAP_URL) 공장 평면도 오버레이
    → 가스센서/전력장비/지오펜스/작업자 더미 마커 레이어 추가
    → setInterval 작업자 이동 애니메이션 (1초)
    → 맵 탭 클릭 → 레이어 on/off

⑦ [initWebSocket()]
    → connect() : new WebSocket('ws://127.0.0.1:8001/ws/sensors/')
```

### 3-C. WebSocket 실시간 데이터 흐름

```
[fastapi-server/websocket.py]
    @app.websocket("/ws/sensors/")
    └── asyncio.sleep(1) 마다 get_temp_sensor_data() 전송
    ⬇ JSON 페이로드 (1초 주기)
    {
      co, h2s, o2, level,
      total_power_mw, power_change_pct,
      equipment: [{name, mwh, temp, level}, ...],
      ai_power_equipment, ai_eta_min,
      ai_max_load_kw, ai_max_load_pct
    }
    ⬇
[dashboard.js → ws.onmessage]
    ┌─────────────────────────────────────────────────────────┐
    │  수신 데이터            DOM 업데이트 대상               │
    │  co, h2s, o2        →  #gasTableBody (tbody innerHTML)  │
    │  co (임계: >50ppm)  →  #aiGasName, #aiCurrentVal,      │
    │                         #aiMaxVal 색상·텍스트 갱신      │
    │  total_power_mw     →  #powerTotal 텍스트               │
    │  power_change_pct   →  #powerChangePct 색상·텍스트     │
    │  equipment[]        →  #powerTableBody (tbody innerHTML) │
    │  ai_power_equipment →  #aiPowerEquipName                │
    │  ai_eta_min         →  #aiPowerEta                      │
    │  ai_max_load_kw/pct →  #aiPowerMaxLoad innerHTML        │
    │  co, ai_max_load_kw →  gasChart, powerChart pushData()  │
    │  co, h2s, o2, level →  MapPanel.updateGasSensorFromWS() │
    │                         → gasMarkers['sensor_01'] 색상  │
    └─────────────────────────────────────────────────────────┘
    ⬇ 연결 끊김 시
    ws.onclose → setTimeout(connect, 5000)  자동 재연결
    #wsStatus  → "● 연결 끊김" (css: .ws-status.error)
```

### 3-D. MN-04 작업자 현황 패널 흐름 (30초 폴링)

```
[dashboard.js → initMN04()]
    ⬇
localStorage.getItem('user_type')
    ┌─────────────────────────────────┬─────────────────────────────────┐
    │  'worker' (기본값)              │  'admin'                        │
    │                                 │                                 │
    │  GET /api/alarms/my-status/     │  GET /api/alarms/worker-summary/│
    │  → { data: { status } }         │  → { data: { total_count,       │
    │                                 │    normal_count, warning_count, │
    │                                 │    danger_count } }             │
    │                                 │                                 │
    │  renderWorkerStatus(data)       │  renderAdminSummary(data)       │
    │  ┌─────────────────────────┐   │  → #mn04-kpi-total/normal/      │
    │  │  status  left   color   │   │    warning/danger 수치 갱신     │
    │  │  normal  16%  #2d9e75   │   │  → #mn04-ratio-bar flex 비율    │
    │  │  warning 50%  #ef9f27   │   │    normal/warning/danger        │
    │  │  danger  84%  #e24b4a   │   │                                 │
    │  └─────────────────────────┘   │                                 │
    │  → #mn04-marker left/color     │                                 │
    │  → #mn04-status-text 텍스트    │                                 │
    └─────────────────────────────────┴─────────────────────────────────┘
    ※ setInterval(30_000) 반복
```

---

## 4. 파일별 역할 (File Changes)

| 순서 | 파일 | 상태 | 역할 |
|------|------|------|------|
| 1 | `templates/main_dashboard.html` | **신규** | 3개 대시보드 통합 단일 HTML. header.html include, 전 패널 포함 |
| 2 | `static/css/dashboard.css` | **신규** | style.css + CJY.css + 인라인 스타일 통합 CSS |
| 3 | `static/js/dashboard.js` | **신규** | main.js + CJY.js + 인라인 맵 JS 통합, WebSocket 버그 수정 |
| 4 | `config/urls.py` | **수정** | 루트/dashboard/ → main_dashboard 뷰로 변경, 기존 경로 하위 호환 유지 |
| 5 | `templates/dashboard_jh.html` | 유지 (하위 호환) | `/dashboard_jh/` 경로로 여전히 접근 가능 |
| 6 | `templates/dashboard_CJY.html` | 유지 (하위 호환) | `/dashboard-cjy/` 경로로 여전히 접근 가능 |
| 7 | `templates/dashboard_sh.html` | 유지 (하위 호환) | `/dashboard_sh/` 경로로 여전히 접근 가능 |
| 8 | `static/js/main.js` | 유지 (기존 파일 참조용) | dashboard_sh.html, dashboard_CJY.html이 여전히 참조 |
| 9 | `static/js/main_jh.js` | 유지 (중복) | dashboard_jh.html 참조. main.js와 완전 동일 내용 |
| 10 | `static/js/CJY.js` | 유지 (기존 파일 참조용) | dashboard_CJY.html이 여전히 참조 |
| 11 | `static/css/style.css` | 유지 (기존 파일 참조용) | 기존 대시보드들이 여전히 참조 |
| 12 | `static/css/CJY.css` | 유지 (기존 파일 참조용) | dashboard_CJY.html이 여전히 참조 |
| 13 | `fastapi-server/websocket.py` | 참조만 (변경 없음) | WebSocket 페이로드 스키마 확인용. dashboard.js가 이 스키마를 기반으로 구현 |

---

## 5. 테스트 방법 (Test Plan)

### 서버 구동
```bash
# FastAPI WebSocket 서버 (터미널 1)
cd fastapi-server
uvicorn websocket:app --host 0.0.0.0 --port 8001 --reload

# Django DRF 서버 (터미널 2)
cd drf-server
python manage.py runserver
```

### 체크리스트

- [ ] `http://localhost:8000/` 접근 시 `main_dashboard.html` 렌더링 확인
- [ ] `http://localhost:8000/dashboard/` 동일 화면 확인
- [ ] 헤더 — 사용자 이름, 시계, 새로고침 버튼, 로그아웃 모달 정상 동작
- [ ] 햄버거 메뉴 클릭 → SNB Drawer 슬라이드 in/out
- [ ] 맵 패널 — Leaflet 지도 공장 평면도 로드, 가스/작업자/지오펜스 마커 표시
- [ ] 맵 탭(전체/작업자/위험구역 등) 클릭 시 레이어 필터 동작
- [ ] `#wsStatus` 배지 — FastAPI 서버 실행 시 "● 실시간 연결", 미실행 시 "● 연결 오류"
- [ ] 유해가스 테이블(패널 12) — WebSocket 수신 시 CO/H₂S/O₂ 실시간 갱신
- [ ] AI 예측 가스 차트(패널 13) — 1초 주기로 꺾은선 그래프 실시간 확장
- [ ] 전력 현황(패널 14) — 전력량/온도/위험도 실시간 갱신
- [ ] AI 예측 전력 차트(패널 15) — 1초 주기로 꺾은선 그래프 실시간 확장
- [ ] Y축 스케일 버튼(+/−/↺) — 가스/전력 차트 범위 조정 동작
- [ ] `user_type = 'worker'` — 작업자 B View(가로 상태 바) 표시
- [ ] `user_type = 'admin'` → `localStorage.setItem('user_type','admin')` 후 새로고침 — 관리자 D View(KPI 카드) 표시
- [ ] 기존 경로 하위 호환 — `/dashboard_jh/`, `/dashboard-cjy/`, `/dashboard_sh/` 각각 정상 접근 확인

---

## 6. 변경 사항 비교 (기존 → 변경)

| 항목 | 기존 | 변경 |
|------|------|------|
| 진입점 URL | `""` → `dashboard_sh.html` | `""` → `main_dashboard.html` |
| 헤더 구현 | dashboard_CJY·dashboard_sh 는 인라인 중복 | 전체 `{% include 'header.html' %}` 통일 |
| CSS 로드 | 페이지마다 style.css + 개별 css 복수 링크 | 단일 `dashboard.css` 1개 링크 |
| JS 로드 | main.js + CJY.js 복수 스크립트 태그 | 단일 `dashboard.js` 1개 스크립트 태그 |
| Leaflet 맵 JS | dashboard_sh.html 내 인라인 230줄 | dashboard.js `MapPanel` 객체로 분리 |
| WebSocket 핸들러 | `ws.onmessage` 정의 누락, `statusDiv` 미정의 → **런타임 오류** | 정상 래핑 + DOM 기반 상태 표시로 수정 |
| 맵 SVG URL | `{% static %}` 태그가 인라인 JS 안에 위치 | `window.FACTORY_MAP_URL` 전역 변수 주입으로 JS 파일 분리 가능 |
| MN-04 패널 | dashboard_CJY.html 에만 존재 | main_dashboard.html 에 통합 |
| main_jh.js | main.js와 완전 동일한 551줄 중복 파일 | dashboard.js 1개로 대체 (main_jh.js 미사용 상태) |
