# 웹소켓 실시간 데이터 패널 (`dashboard.html` + `main.js`)

## 개요

대시보드 하단 패널(12 · 13 · 14 · 15번)은 FastAPI WebSocket 서버로부터
1초 주기로 수신되는 더미 데이터를 실시간으로 표시합니다.

---

## 패널 구성

| 패널 | 제목 | 데이터 출처 |
|------|------|------------|
| 12번 | 내 근처 유해가스 위험 현황 | WebSocket (`co`, `h2s`, `o2`) |
| 13번 | AI 예측 — 내 근처 유해가스 위험 | WebSocket (`co` × 1.5 시뮬레이션) |
| 14번 | 스마트 전력 시스템 위험 현황 | WebSocket (`total_power_mw`, `equipment`) |
| 15번 | AI 예측 — 스마트 전력 시스템 위험 | WebSocket (`ai_power_equipment`, `ai_eta_min`, `ai_max_load_kw`) |

---

## WebSocket 연결

| 항목 | 값 |
|------|----|
| 서버 | FastAPI (`fastapi-server/websocket.py`) |
| 엔드포인트 | `ws://localhost:8001/ws/sensors/` |
| 전송 주기 | 1초 |
| 포맷 | JSON |

---

## 수신 데이터 구조

```json
{
  "device_id": "sensor-01",
  "timestamp": "2026-04-15T12:00:00.000000",

  // 유해가스 (패널 12·13)
  "co":  12,
  "h2s": 3,
  "o2":  20.7,
  "level": "정상",

  // 전력 시스템 (패널 14)
  "total_power_mw": 1243,
  "power_change_pct": 15.5,
  "equipment": [
    { "name": "압연기",      "mwh": 15.1, "temp": 127, "level": "danger"  },
    { "name": "송풍기",      "mwh": 14.8, "temp": 124, "level": "danger"  },
    { "name": "집진기",      "mwh": 5.3,  "temp": 122, "level": "caution" },
    { "name": "전자기 교반기","mwh": 3.5,  "temp": 125, "level": "safe"    }
  ],

  // AI 예측 (패널 15)
  "ai_power_equipment": "압연기",
  "ai_eta_min": 28,
  "ai_max_load_kw": 16200,
  "ai_max_load_pct": 107
}
```

---

## 패널별 업데이트 동작

### 패널 12 — 유해가스 위험 현황

| DOM ID | 업데이트 내용 |
|--------|-------------|
| `#gasTableBody` | CO · H₂S · O₂ 농도 및 위험도 행 재렌더링 |

위험도 판정 기준

| 가스 | 위험 조건 |
|------|----------|
| CO   | > 50 ppm |
| H₂S  | > 10 ppm |
| O₂   | < 19.5 % |

---

### 패널 13 — AI 예측 유해가스

| DOM ID | 업데이트 내용 |
|--------|-------------|
| `#aiGasName` | CO 위험 여부에 따라 `danger-text` / `caution-text` 클래스 전환 |
| `#aiCurrentVal` | 현재 CO 농도 (ppm) |
| `#aiMaxVal` | 12시간 내 예상 최대 농도 (`co × 1.5`) |
| `#chartGas` (canvas) | 실시간 라인 차트 — 현재 농도 · 예측 최대 농도 |

---

### 패널 14 — 스마트 전력 시스템 위험 현황

| DOM ID | 업데이트 내용 |
|--------|-------------|
| `#powerTotal` | 전체 전력 사용량 (MW) |
| `#powerChangePct` | 기준 대비 변화율 (`▲ +N%` / `▼ N%`) |
| `#powerTableBody` | 설비명 · 전력 사용량(MWh) · 온도(°C) · 위험도 행 재렌더링 |

위험도 표시 기준

| level | 표시 | 클래스 |
|-------|------|--------|
| `danger`  | 위험 | `brisk danger`  |
| `caution` | 주의 | `brisk caution` |
| `safe`    | 정상 | `brisk safe`    |

---

### 패널 15 — AI 예측 스마트 전력

| DOM ID | 업데이트 내용 |
|--------|-------------|
| `#aiPowerEquipName` | 위험 설비명 (가장 높은 risk 기준) |
| `#aiPowerEta` | 위험 도달 예상 시간 (`N 분 뒤`) |
| `#aiPowerMaxLoad` | 12시간 내 예상 최대 부하 (`N kW (정상 대비 N%)`) |
| `#chartPower` (canvas) | 실시간 라인 차트 — AI 예측 최대 부하 (kW) |

---

## Chart.js 실시간 시각화

### 개요

| 항목 | 값 |
|------|----|
| 라이브러리 | Chart.js v4 (CDN) |
| 적용 패널 | 13번 (`#chartGas`), 15번 (`#chartPower`) |
| 갱신 방식 | `ws.onmessage` 수신 시마다 `chart.update('none')` |
| 슬라이딩 윈도우 | 최근 30개 포인트 유지, 초과 시 앞에서 `shift()` |

### 차트 구성

| 차트 | 데이터셋 | 색상 |
|------|---------|------|
| `gasChart` (13번) | 현재 농도 (ppm) | 주황 `#f59e0b` |
| `gasChart` (13번) | 예측 최대 농도 (ppm, 점선) | 빨강 `#ef4444` |
| `powerChart` (15번) | 예상 최대 부하 (kW) | 빨강 `#ef4444` |

### Y축 스케일 조절 기능

패널 13 · 15 차트 상단에 스케일 컨트롤 바 제공.

| 버튼 | 동작 | 배율 |
|------|------|------|
| `+` | 범위 축소 (확대) | 현재 Y최대 × 0.75 |
| `−` | 범위 확대 (축소) | 현재 Y최대 × 1.35 |
| `↺` | 자동 스케일 복귀 | Chart.js 자동 계산 |

- 현재 Y최대값은 버튼 사이 숫자로 표시, 자동 상태일 때는 `자동` 표시
- `scaleState` 객체(`gas` / `power` 키)로 각 차트의 Y최대값 개별 관리

---

## 더미 데이터 생성 로직 (`fastapi-server/websocket.py`)

| 항목 | 생성 방식 |
|------|----------|
| `co` / `h2s` / `o2` | 10% 확률로 위험 범위, 나머지 정상 범위 난수 |
| `total_power_mw` | 1,200 MW 기준 ±변동 난수 |
| `power_change_pct` | `(total_power_mw − 1076) / 1076 × 100` |
| 설비별 `mwh` | 기준값(`base_mwh`) ± 0.5 MWh 난수 |
| 설비별 `temp` | 기준값(`125°C`) ± 난수 |
| `ai_eta_min` | 15 ~ 40분 난수 |
| `ai_max_load_kw` | 설비 mwh × 1,000 × 1.05 ~ 1.2 |

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `fastapi-server/websocket.py` | WebSocket 서버 · 더미 데이터 생성 |
| `drf-server/templates/dashboard.html` | 패널 DOM ID 정의, canvas 요소, 스케일 컨트롤 버튼, Chart.js CDN |
| `drf-server/static/css/style.css` | `.panel-chart` · `.chart-wrap` · `.scale-btn` 스타일, `bottom-row` 높이 |
| `drf-server/static/js/main.js` | `ws.onmessage` 핸들러 · 차트 초기화 · `adjustYScale()` 스케일 조절 함수 |
