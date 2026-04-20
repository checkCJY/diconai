# 리팩토링 보고서 v2 — 버그 수정 3건

> 작성일: 2026-04-16
> 브랜치: `feature/mn-04.v1`
> 기준 문서: `docs/refactoring_report.md` (v1 통합 작업)


---

## 1. 요약 (Summary)

**통합 대시보드(`main_dashboard.html`) 적용 후 발견된 3가지 버그(모달 렌더링 위치, 맵 여백, 알람 팝업 누락)를 CSS z-index 조정 및 JS 모듈 추가로 수정.**

---

## 2. 주요 변경 사항 (Key Changes)

### Bug Fix 1 — 로그아웃 모달이 Leaflet 맵 뒤에 렌더링
- **파일**: `static/css/dashboard.css`
- `.snb-overlay` z-index: `200` → `800`
- `.snb-drawer` z-index: `201` → `801`
- `.modal-backdrop` z-index: `300` → `1000`
- `#alarm-popup` z-index: `1100` (신규 추가, 모달보다 위)

### Bug Fix 2 — Leaflet 맵 컨테이너 여백 미해소
- **파일**: `static/css/dashboard.css`
- `.map-area` — `display:flex; align-items:center; justify-content:center` 제거 → `position:relative` 로 전환
- `#map` — `width/height:100%` 방식에서 `position:absolute; inset:0` 방식으로 전환

### Bug Fix 3 — 통합 대시보드에서 위험 알람 팝업 미작동
- **파일**: `templates/main_dashboard.html`
  `#alarm-popup` DOM 블록 추가 (헤더: 레벨 + 닫기 버튼, 본문: 메시지 + 메타, 확인 버튼)
- **파일**: `static/js/dashboard.js`
  `AlarmPopup` 객체 신규 추가 (큐 기반 show/close/init)
  `initWebSocket()` → `ws.onmessage` 내 `data.level === '위험'` 조건 시 팝업 트리거
  `initApp()` 내 `AlarmPopup.init()` 호출 추가

---

## 3. 데이터 흐름도 (Data Flow)

### Fix 1 — z-index 스택 구조 변경

```
[기존 z-index 스택]                     [수정 후 z-index 스택]

Leaflet popup pane   : 700              #alarm-popup         : 1100
Leaflet marker pane  : 600              .modal-backdrop      : 1000
.modal-backdrop      : 300  ← 문제      .snb-drawer          :  801
.snb-drawer          : 201  ← 문제      .snb-overlay         :  800
.snb-overlay         : 200  ← 문제      Leaflet popup pane   :  700
Leaflet tile pane    : 200              Leaflet marker pane  :  600
                                        Leaflet tile pane    :  200
```

모달이 Leaflet 레이어 아래에 렌더링되던 문제 해소.
`position:fixed` 임에도 Leaflet이 내부에서 높은 z-index 레이어를 생성하기 때문에 발생한 충돌이었음.

> 그러나 원하는 만큼 적용이 안되었음. 추가적인 해결 방안을 찾아봐야 할 듯 함.

---

### Fix 2 — 맵 컨테이너 높이 계산 방식 변경

```
[기존 흐름]

.panel-map (flex-direction:column)
    ⬇
.map-area (display:flex; align-items:center; justify-content:center)
    ⬇
#map (height:100%)
    └── flex 자식의 높이는 align-items:center 기준 → content 크기로 고정
        → Leaflet이 부모 높이를 인식 못해 여백 발생

[수정 후 흐름]

.panel-map (flex-direction:column)
    ⬇
.map-area (position:relative; flex:1; overflow:hidden)
    ⬇
#map (position:absolute; inset:0)
    └── 부모의 top/right/bottom/left 기준으로 완전히 채움
        → Leaflet이 컨테이너를 정확히 인식하여 여백 없이 렌더링
```

---

### Fix 3 — 알람 팝업 흐름 통합

```
[기존 흐름 — alarm_panel.html 전용]

[alarm_panel.html] /alarm/ 페이지만 해당
    └── 인라인 WebSocket → data.level === '위험' → showPopup()
    → main_dashboard.html 에는 팝업 없음 (누락)


[수정 후 흐름 — main_dashboard.html 통합]

[fastapi-server/websocket.py]
    asyncio.sleep(1) 마다 JSON 전송
    { level: "위험" or "정상", co, h2s, o2, device_id, timestamp, ... }
    ⬇
[dashboard.js → ws.onmessage]
    ① 패널 12~15 데이터 갱신 (기존)
    ② MapPanel.updateGasSensorFromWS(data) (기존)
    ③ data.level === '위험' ? AlarmPopup.show({...}) : (무시)  ← 신규
    ⬇
[AlarmPopup.show(data)]
    popupQueue.push(data)
    ┌─────────────────────────────────────────────────────┐
    │  isOpen === false → _process() 즉시 실행            │
    │  isOpen === true  → 큐에 쌓임, 현재 팝업 닫힌 후   │
    │                     500ms 뒤 다음 항목 처리         │
    └─────────────────────────────────────────────────────┘
    ⬇
[AlarmPopup._process()]
    #alarm-popup-level   ← "🔴 위험" (color: var(--danger))
    #alarm-popup-message ← "CO: Xppm / H₂S: Xppm / O₂: X%"
    #alarm-popup-meta    ← "sensor-01 | HH:MM:SS"
    #alarm-popup         ← display: 'block'
    setTimeout(close, 10000)  ← 10초 자동 닫힘
    ⬇
[닫힘 조건]
    ├── 10초 경과 → 자동 close()
    ├── ✕ 버튼 클릭 → close()
    └── 확인 버튼 클릭 → close()
        ⬇ 500ms 후 → _process() → 큐에 항목 있으면 다음 팝업 표시
```

---

## 4. 파일별 역할 (File Changes)

| 순서 | 파일 | 변경 유형 | 변경 내용 |
|------|------|-----------|-----------|
| 1 | `static/css/dashboard.css` | **수정** | z-index 3곳 상향 (snb-overlay·snb-drawer·modal-backdrop), #map position:absolute 전환, .map-area flex→position 전환, #alarm-popup 스타일 추가 |
| 2 | `templates/main_dashboard.html` | **수정** | `#alarm-popup` DOM 블록 추가 (팝업 헤더·메시지·메타·확인 버튼) |
| 3 | `static/js/dashboard.js` | **수정** | `AlarmPopup` 객체 추가, `ws.onmessage` 에 위험 트리거 추가, `initApp()`에 `AlarmPopup.init()` 추가 |

---

## 5. 테스트 방법 (Test Plan)

### Fix 1 — 모달 렌더링 확인
- [ ] `http://localhost:8000/` 접속 후 로그아웃 버튼 클릭
- [X] 모달이 **맵 위에** 오버레이 형태로 화면 중앙에 표시되는지 확인
- [X] 취소 버튼으로 모달 닫힘 확인
- [X] 햄버거 메뉴 클릭 시 SNB Drawer가 맵 위에 정상 표시되는지 확인

### Fix 2 — 맵 여백 확인
작동이 안되는 것으로 파악됨, 수정이 필요함
- [ ] 맵 패널 영역에 여백(빈 공간) 없이 공장 평면도가 꽉 채워지는지 확인
- [ ] 브라우저 창 크기 변경 시에도 맵이 컨테이너에 맞게 리사이즈되는지 확인

### Fix 3 — 알람 팝업 확인
```bash
# FastAPI 서버 실행 후
cd fastapi-server && uvicorn websocket:app --port 8001 --reload
```
- [X] `http://localhost:8000/` 에서 WebSocket 연결 후 `data.level === '위험'` 수신 시 우측 상단 팝업 표시 확인 (FastAPI는 10% 확률로 위험 데이터 발생)
- [X] 팝업에 CO/H₂S/O₂ 수치, sensor_id, 시각 표시 확인
- [X] 10초 후 자동 닫힘 확인
- [X] ✕ 버튼 / 확인 버튼으로 수동 닫힘 확인
- [] 연속 위험 발생 시 큐 처리로 팝업이 순서대로 표시되는지 확인
-> 이 부분에서 큐 처리로 팝업이 순서대로 표시되는것 말고, 알람이 쌓이는 방식으로 하는게 좋지 않을까 하는 생각.

---

## 6. 변경 사항 비교

| 항목 | v1 (통합 직후) | v2 (버그 수정 후) |
|------|---------------|-----------------|
| 로그아웃 모달 위치 | Leaflet 맵 레이어 뒤에 렌더링 | 전체 화면 위 z-index:1000 으로 정상 표시 |
| SNB Drawer | Leaflet 마커 뒤에 렌더링될 수 있음 | z-index:801 로 맵 위에 정상 표시 |
| Leaflet 맵 여백 | `.map-area` flex 중앙정렬로 여백 발생 | `position:absolute; inset:0` 으로 컨테이너 완전 채움 |
| 위험 알람 팝업 | `main_dashboard.html` 에 없음 (alarm_panel.html 전용) | WebSocket onmessage → AlarmPopup.show() 통합 |
| 알람 팝업 큐 | 없음 | 큐 기반으로 연속 알람 순서 처리 |
