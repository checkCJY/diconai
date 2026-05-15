# monitoring_realtime 페이지 — dashboard/websocket.js 의존성 누락

**발견일**: 2026-05-15 (Phase 2 알람 인프라 검증 중)
**상태**: 미해결 — 본 페이지 작업자에게 fix 결정 위임
**시연 영향**: 시연 시 이 페이지 제외하기로 결정

---

## 증상

`/dashboard/monitoring/realtime/` 페이지 진입 시 브라우저 Console 에 다음과 같은 에러가 반복:

```
[WSClient] handler error ReferenceError: powerChart is not defined
   at _switchPowerChart (websocket.js:110:3)
   at _renderAIPowerNav (websocket.js:144:3)
   at websocket.js:375:9
   at ws-client.js:76:15
   at Set.forEach (<anonymous>)
   at _dispatch (ws-client.js:75:11)
   at ws.onmessage (ws-client.js:108:9)
```

부수 영향:
- 위험·주의 알람 발생해도 팝업·이벤트 패널 미동작
- WS 자체는 `/ws/sensors/` 정상 연결 (status 101)

---

## 원인

`templates/snb_details/monitoring_realtime.html` (line 194) 가 `dashboard/websocket.js` 를 그대로 로드함. 그러나 dashboard 페이지 전용 의존성이 같이 로드되지 않아서, onMessage handler 안에서 미선언 변수에 접근 → `ReferenceError`.

JavaScript ES6 의 `let`/`const` 변수는 hoisting 되지 않으므로, 선언 자체가 없는 파일에서 그 변수에 접근 시 `ReferenceError` 가 던져집니다 (`var` 와 다름).

### typeof 진단 결과 (2026-05-15 monitoring_realtime 페이지 Console)

| 변수 | 정의 위치 | 페이지 상태 |
|---|---|---|
| `powerChart` | `static/js/dashboard/charts.js` | ❌ `undefined` (charts.js 미로드) |
| `gasChart` | `static/js/dashboard/charts.js` | ❌ `undefined` |
| `EventPanel` | `static/js/dashboard/panels/event-panel.js` | ❌ `undefined` |
| `MapPanel` | `static/js/dashboard/panels/map-panel.js` | ✅ `object` (페이지에 지도 있음) |
| `_aiPowerHist` | `dashboard/websocket.js` module-level | ✅ `object` (websocket.js 안에서 정의) |

### 핵심 흐름

```
WS 메시지 도착
  → ws-client.js: _dispatch → 등록된 handler 호출
  → dashboard/websocket.js 의 onMessage handler 실행
  → handler 안에서 _renderAIPowerNav() 호출
  → _renderAIPowerNav() 가 _switchPowerChart() 호출
  → _switchPowerChart() 의 `!powerChart` 평가 시점에 ReferenceError
  → handler 중단 (그 뒤의 알람 처리 코드 미실행)
```

---

## 페이지 본 목적과 의존성 불일치

`monitoring_realtime` 은 **지도 중심 페이지** (MapPanel 만 보유). 그러나 `dashboard/websocket.js` 는 dashboard 페이지의 모든 패널 (가스 차트, 전력 차트, AI 전력 예측 패널, 이벤트 패널, 지도, 알람) 을 통합 갱신하는 코드 — 지도 페이지에서 그대로 사용하는 것은 설계상 부적절.

---

## 관련 파일·라인

| 파일 | 라인 | 역할 |
|---|---|---|
| `templates/snb_details/monitoring_realtime.html` | 194 | `dashboard/websocket.js` 를 로드하는 지점 |
| `static/js/dashboard/websocket.js` | 110 | `_switchPowerChart` — 첫 ReferenceError 발생점 |
| `static/js/dashboard/websocket.js` | 119 | `_renderAIPowerNav` — _switchPowerChart 호출 |
| `static/js/dashboard/websocket.js` | 375 | onMessage handler 안에서 _renderAIPowerNav 호출 |
| `static/js/dashboard/charts.js` | — | `powerChart`/`gasChart` 정의 위치 (미로드) |
| `static/js/dashboard/panels/event-panel.js` | — | `EventPanel` 정의 위치 (미로드) |

---

## 영향 범위

- 본 페이지에서 모든 실시간 WS 데이터 처리가 미동작 (알람뿐 아니라 가스/전력 데이터 갱신도)
- dashboard 페이지에는 영향 없음 (의존성 모두 로드됨)
- 다른 snb_details 페이지에는 영향 없음 (해당 페이지들은 `dashboard/websocket.js` 를 로드하지 않음 — 확인 필요)

---

## 검증 방법

브라우저 DevTools → Console 탭에서:

```js
typeof powerChart   // "undefined"
typeof gasChart     // "undefined"
typeof EventPanel   // "undefined"
typeof MapPanel     // "object"
```

또는 페이지 진입 후 Console 의 빨간 ReferenceError 메시지 확인.

---

## Fix 방향 옵션

작업자가 페이지 의도·시간 여유·향후 유지보수 부담을 고려해 선택. **권장 옵션을 prescribe 하지 않음** — 페이지 작업자의 컨텍스트가 우선.

### 옵션 1 — typeof guard 추가 (surgical, 임시)
`_switchPowerChart`, `_renderAIPowerNav`, 그리고 EventPanel 사용 부분 등 각 호출 지점에 `typeof <var> === 'undefined'` 가드 추가.
- 코드 변경량: 적음 (수정 위치 3~5곳)
- 장점: 즉시 적용, dashboard 페이지에 영향 0
- 단점: 향후 새 변수 의존 추가될 때 같은 가드 누락 위험 (두더지 잡기 패턴)
- 적용 범위: monitoring_realtime 의 알람 처리만 정상 동작. chart·EventPanel 갱신은 여전히 미실행 (페이지에 그 DOM 자체가 없어서 의도된 결과).

### 옵션 2 — monitoring_realtime 페이지의 WS 책임 분리
`monitoring_realtime.html` 에서 `dashboard/websocket.js` 제거. 이 페이지에 필요한 동작 (지도 갱신 + 알람) 만 별도 JS 로 처리.
- 코드 변경량: 중간 (페이지 전용 WS 핸들러 신설)
- 후보 구성:
  - 알람: `components/alarm_stack.html` partial include (Phase 2 가 만든 인프라 활용)
  - 지도: `dashboard/panels/map-panel.js` + 페이지 전용 onMessage 핸들러 (worker_positions 처리)
- 장점: 책임 분리 — 페이지가 사용하지 않는 chart·EventPanel 의존성 자체 제거
- 단점: 페이지 전용 WS 코드 작성 + 회귀 위험

### 옵션 3 — monitoring_realtime 에 누락된 의존성 추가
charts.js + event-panel.js + DOM 마크업 (alarm panel 등) 을 페이지에 추가.
- 코드 변경량: 큼 (DOM·CSS·JS 모두)
- 장점: 코드 구조 변경 없음
- 단점: 지도 중심 페이지에 차트·이벤트 패널 의존성이 자라남 (페이지 의도 부풀음)

### 옵션 4 — `dashboard/websocket.js` 자체 분리 (구조 개선)
chart 갱신, map 갱신, alarm 처리, gas/power 데이터 처리 등을 별도 모듈로 분리하고 각 페이지가 필요한 모듈만 로드.
- 코드 변경량: 매우 큼 (websocket.js 리팩토링 + 모든 사용 페이지 영향)
- 장점: 본 버그뿐 아니라 향후 비슷한 의존성 충돌 근본 해소
- 단점: 리팩토링 범위가 알람·차트·지도 모두라 회귀 위험 큼, 별도 sprint 필요

---

## 참고 — 다른 페이지의 같은 패턴 확인 필요

`dashboard/websocket.js` 를 로드하는 다른 snb_details 페이지가 있다면 같은 증상 가능. grep 으로 확인:

```bash
grep -rln "dashboard/websocket.js" drf-server/templates/
```

대부분 dashboard 페이지에서만 로드돼 있어야 정상.
