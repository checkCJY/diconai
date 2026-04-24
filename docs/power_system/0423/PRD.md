# 요구사항 정의서 — 전력 차트 임계치 기준 개정 [PWR-THRESHOLD-001]

> 작성일: 2026-04-23
> 작업 브랜치: `feature/section-11.v3`
> 대상 파일: `drf-server/static/js/refactors/charts_CJY.js`

---

## 1. 기본 정보

| 항목 | 내용 |
|---|---|
| **기능명** | 전력 패널 실시간 차트 임계치 시각화 |
| **중요도** | 상 |
| **관련 화면/컴포넌트** | 메인 대시보드 전력 패널 (`#chartPower`) |
| **관련 파일** | `charts_CJY.js`, `main_dashboard_CJY.html` |

---

## 2. 비즈니스 로직 및 기능 요구사항

### 2.1 임계치 기준 (Phase A 고정값)

패널 단위 전력 기준으로 3단계 구간을 정의한다.

| 단계 | 범위 | 시각화 색상 |
|---|---|---|
| 안전 | 0 ~ 2,200 kW | (기본 배경 — 별도 표시 없음) |
| 주의 | 2,200 ~ 2,860 kW | 황색 반투명 띠 + 황색 점선 |
| 위험 | 2,860 kW 이상 | 적색 반투명 띠 + 적색 점선 |

> 위험 하한 = 주의 하한 × 1.3 = 2,200 × 1.3 = **2,860 kW**

### 2.2 선행 조건

- Chart.js 4 및 `chartjs-plugin-annotation` 3 이 CDN으로 로드된 상태
- `#chartPower` canvas 요소가 DOM에 존재

### 2.3 기본 흐름

1. 페이지 로드 시 `initCharts()` 호출
2. `POWER_THRESHOLD_WARNING(2200)` / `POWER_THRESHOLD_DANGER(2860)` 상수로 annotation 생성
3. 차트 Y축에 주의·위험 경계선 및 배경 띠 렌더링
4. WebSocket으로 `예상 최대 부하 (kW)` 데이터 수신 시 실시간 갱신

### 2.4 후행 조건

- 차트에 주의·위험 구간 시각적 경계가 항상 표시됨
- 데이터 값이 임계치를 넘으면 사용자가 차트에서 즉시 인지 가능

---

## 3. 예외 및 에러 처리

| 상황 | 처리 방식 |
|---|---|
| `#chartPower` 요소 없음 | `powerChart = null` — annotation 관련 오류 없이 무시 |
| Phase B 전환 시 동적 임계치 수신 | `updatePowerThresholds(warnKw, dangerKw)` 호출로 annotation 교체 |

---

## 4. Phase B 전환 조건

페이로드에 `threshold_warning_kw` / `threshold_danger_kw` 키가 추가되면 Phase B로 전환.
`websocket_CJY.py` → `_build_broadcast_payload()` 에 두 키 추가 필요.

```javascript
// ws.onmessage 내 분기 예시
if (data.threshold_warning_kw !== undefined)
  updatePowerThresholds(data.threshold_warning_kw, data.threshold_danger_kw);
```

---

## 5. 비기능적 요구사항

| 항목 | 기준 |
|---|---|
| 렌더링 성능 | `chart.update('none')` — 애니메이션 없이 즉시 갱신 |
| 반응형 | `responsive: true`, `maintainAspectRatio: true` |
| Y축 가독성 | stepSize 1,000 kW 간격, 천 단위 쉼표(`toLocaleString`) |
