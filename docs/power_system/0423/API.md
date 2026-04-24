# API 명세서 — 전력 차트 임계치 관련 [PWR-THRESHOLD-001]

> 작성일: 2026-04-23
> 대상 파일: `drf-server/static/js/refactors/charts_CJY.js`

---

## 1. 신규 추가 파일 및 수정 파일

```text
drf-server/static/js/refactors/
└── charts_CJY.js          # [Chart] 전력 차트 임계치 상수 및 annotation 설정 수정

```

---

## 2. 프론트엔드 공개 함수 (JS API)

### 2.1 `initCharts()`

차트 초기화 및 Phase A 고정 임계치 annotation 적용.

- **호출 시점**: 페이지 DOMContentLoaded 또는 `main_dashboard_CJY.html` 인라인 스크립트
- **사이드이펙트**: `gasChart`, `powerChart` 전역 변수 설정

---

### 2.2 `updatePowerThresholds(warnKw, dangerKw)`

Phase B 전환 시 WebSocket 페이로드 수신 값으로 임계치 동적 교체.

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `warnKw` | `number` | 주의 하한 (kW) |
| `dangerKw` | `number` | 위험 하한 (kW) |

- **호출 위치**: `ws.onmessage` 내 조건 분기
- **조건**: `data.threshold_warning_kw !== undefined`

---

### 2.3 `adjustYScale(key, chart, direction)`

Y축 수동 줌 조절. 전력 차트 전용 step = **1,000 kW**.

| 파라미터 | 값 | 동작 |
|---|---|---|
| `direction` | `+1` | 스케일 축소 (−1,000 kW) |
| `direction` | `-1` | 스케일 확대 (+1,000 kW) |
| `direction` | `0` | 자동 스케일 복원 |

---

## 3. WebSocket 수신 페이로드 명세

### 3.1 Phase A (현재) — 정적 임계치

임계치는 JS 상수로 고정, 페이로드에 임계치 키 없음.

```jsonc
// ws.onmessage data 예시
{
  "total_kw": 1850.0,
  "equipment": [ ... ]
}
```

### 3.2 Phase B (예정) — 동적 임계치

```jsonc
{
  "total_kw": 1850.0,
  "threshold_warning_kw": 2200,   // 추가 필요
  "threshold_danger_kw":  2860,   // 추가 필요
  "equipment": [ ... ]
}
```

> **백엔드 작업 필요**: `fastapi-server/websocket_CJY.py` → `_build_broadcast_payload()` 에 두 키 추가.

---

## 4. 임계치 상수 변경 이력

| 상수 | 변경 전 | 변경 후 | 비고 |
|---|---|---|---|
| `POWER_THRESHOLD_WARNING` | `20` kW | `2200` kW | 패널 기준 안전 상한 |
| `POWER_THRESHOLD_DANGER` | `28` kW | `2860` kW | `Math.round(2200 * 1.3)` |
| Y축 `stepSize` | `10000` | `1000` | kW 단위 가독성 개선 |
| 줌 버튼 `step` | `10000` | `1000` | `adjustYScale` 내 power 분기 |
| 위험 경계선 레이블 | `'위험'` | `'위험'` | 중간 `'초과'` 시도 후 원복 |
