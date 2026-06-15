# AI 예측 그래프 구현 Plan (가스/전력 모니터링)

> 대상 페이지
> - `http://localhost:8000/dashboard/monitoring/gas/`
> - `http://localhost:8000/dashboard/monitoring/power/`
>
> 목적: "AI 예측" 탭 그래프를, 단순 실시간 수치 표시에서 **명세상의 "측정값(실선) + AI 예측값(점선)" 통합 추이 그래프**로 전환하기 위해 코드베이스에 무엇을 추가/수정해야 하는지 정리한 구현 계획. (※ 본 문서는 설계 문서이며 코드는 변경하지 않음)

---

## 0. 한 줄 요약

- **프론트는 거의 준비됨** — Chart.js 인프라·임계치 플러그인·`nowMarker` 플러그인이 이미 존재. 막대(bar)→선(line) 전환 + 점선 데이터 결합이 핵심.
- **진짜 작업 본체는 백엔드** — 현재 ARIMA는 **1-step(다음 한 시점)** 만 산출. 명세가 요구하는 "미래 점선 시계열 / ETA(위험 도달 예상 시간) / 예상 최대 부하"는 **multi-step 예측 + 서빙 API + ETA 계산**을 신규로 추가해야 함.
- **가스는 추론 경로에 ARIMA가 연결조차 안 됨** (pkl 로드만, 실제 탐지는 Isolation Forest). 가스 점선을 그리려면 ARIMA 추론 경로부터 신규 연결 필요.

---

## 1. 현재 상태 (코드 근거)

### 1.1 프론트 — AI 탭이 실시간 캐시를 재표시
| 위치 | 현재 동작 |
|---|---|
| [power_system.js:313](../../../drf-server/static/js/detail/power_system.js#L313) `switchTab('ai')` | 주석 `/* AI 모델 미연동 — 실시간 캐시 데이터로 대체 표시. TODO(4차): AI 예측 API 연동으로 교체 */` → `renderGrid(_lastEquipCache)` |
| [gas_monitoring.js:451](../../../drf-server/static/js/detail/gas_monitoring.js#L451) `switchGasTab('ai')` | `renderGasGrid(_lastGasData)` — 실시간 캐시 재사용 |
| `monitoring_gas.html` / `monitoring_power.html` | "AI 예측 모델 미연동" 공지 배너 표출 중 |

- 차트 형태: **막대(bar) 차트** (`createGasChart` / `createBarChart`). 명세의 "실선→점선 연속 시계열"과는 형태부터 다름 → **line 차트 신규 필요**.

### 1.2 백엔드 — ARIMA는 1-step만
| 위치 | 현재 동작 / 한계 |
|---|---|
| [fastapi-server/ai/router.py:265](../../../fastapi-server/ai/router.py#L265) `_arima_forecast()` | `get_forecast(steps=1)` **하드코딩**. 반환 = 단일 스칼라 `forecast` + `ci_lower/ci_upper/actual/is_violation` |
| [power/services/anomaly_inference.py:314](../../../fastapi-server/power/services/anomaly_inference.py#L314) | 전력은 `_arima_forecast` 호출하나 **violation 판정 + 단일 예측값 feature 저장**에만 사용 |
| [gas/services/gas_service.py:66](../../../fastapi-server/gas/services/gas_service.py#L66) | 가스는 `arima_*.pkl` **로드만**, 추론은 IF 전용. ARIMA는 잔차 feature로만 선택 사용 |
| [apps/ml/models/ml_anomaly_result.py](../../../drf-server/apps/ml/models/ml_anomaly_result.py) | `feature_snapshot_json`에 단일 `arima_forecast`만. **미래 배열 필드 없음** |
| ETA / leadtime | **관련 코드 전무** |

### 1.3 이미 재활용 가능한 자산 (프론트)
| 자산 | 위치 | 용도 |
|---|---|---|
| `thresholdZones` 플러그인 | [chart-helpers.js:81](../../../drf-server/static/js/shared/chart-helpers.js#L81) | 임계치 dashed 라인 + chip → **그대로 사용** |
| `nowMarker` 플러그인 | [chart-helpers.js:214](../../../drf-server/static/js/shared/chart-helpers.js#L214) | **AI 예측용 "지금" 시점 마커 — 이미 작성됨, 현재 미사용** |
| `safeBand` 플러그인 | [chart-helpers.js:151](../../../drf-server/static/js/shared/chart-helpers.js#L151) | O2 안전범위 색칠 → 3단계 zone으로 확장 활용 |
| `CHART_COLOR` 팔레트 | [chart-helpers.js:22](../../../drf-server/static/js/shared/chart-helpers.js#L22) | ok/warn/danger 색 → zone/선 색에 재사용 |
| 임계치 API | `/api/monitoring/gas/thresholds/`, `/api/monitoring/power/threshold-meta/`, `/channel-meta/` | 임계치 선·zone 경계값 공급 → **그대로 사용** |

---

## 2. 명세 항목별 갭 분석

| 명세 요소 | 상태 | 추가 작업 |
|---|---|---|
| 측정값 **실선** | 🟡 데이터는 있음 | line 차트 신규 + 측정 시계열 fetch |
| AI 예측 **점선** | ❌ 데이터 없음 | **multi-step 예측 시계열 신규** (핵심 블로커) |
| 임계치 선 (주황/빨강) | ✅ 있음 | `thresholdZones` 재사용 |
| 배경 zone 색칠 (정상/주의/위험) | 🟡 부분 | `safeBand` 확장 → 3단계 영역 |
| "지금" 시점 마커 | ✅ 있음 | `nowMarker` 연결만 |
| 인사이트 배지 ("현재 농도 20.5%") | 🟡 | 프론트 텍스트 카드 |
| 수직 가이드라인 + 플로팅 툴팁 | 🟡 | Chart.js 툴팁 + 커서 추종 수직선 플러그인 소량 |
| "약 782분 뒤 위험 도달" (ETA) | ❌ 없음 | **ETA 계산 로직 신규** |
| "12시간 내 예상 최대 부하 450kW" | ❌ 없음 | **multi-step 예측 + max 집계 신규** |

---

## 3. 추가해야 할 것 — 백엔드 (작업 본체)

### B-1. multi-step ARIMA forecast
- **수정** [fastapi-server/ai/router.py:265](../../../fastapi-server/ai/router.py#L265) `_arima_forecast()`
  - `get_forecast(steps=1)` → `steps=N` 파라미터화 (기본 1 유지로 기존 호출 하위호환).
  - 반환 구조 확장:
    ```
    {
      "forecast": [..N개..],          # 미래 예측 평균
      "ci_lower": [..N개..],          # 신뢰구간 하한
      "ci_upper": [..N개..],          # 신뢰구간 상한
      "actual": float,
      "is_violation": bool,           # 기존 호환(1-step 기준)
      "horizon": N,
    }
    ```
  - ⚠️ 단일 스칼라를 쓰는 기존 호출부([anomaly_inference.py:314](../../../fastapi-server/power/services/anomaly_inference.py#L314))가 깨지지 않도록 **반환 shape 변경 시 호출부 동시 수정** 또는 별도 함수 분리(`_arima_forecast_series`) 권장.

### B-2. 예측 시계열 서빙 API
- **신규** 엔드포인트. 그래프 1장 = `(과거 측정 시계열) + (미래 예측 시계열)` 한 번에 반환.
  - 후보: `GET /ai/forecast?sensor_type=&sensor_identifier=&horizon=`
  - 반환: 측정 구간(timestamps+values) + 예측 구간(timestamps+forecast+ci) + threshold 메타.
  - 측정 시계열 출처: 기존 측정 데이터 조회 경로 재사용 (전력/가스 raw 조회 selector).
  - 활성 ARIMA 모델 메타는 기존 `_fetch_active_model_meta()` ([ai/router.py:83](../../../fastapi-server/ai/router.py#L83)) 재사용.

### B-3. ETA / 예상 최대 부하 계산
- **신규** 헬퍼 (예: `ai/forecast_eta.py`)
  - **ETA**: 예측 시계열 `forecast[]`가 주의/위험 임계치를 처음 교차하는 step → 시간 환산("약 N분 뒤").
  - **예상 최대 부하**: 예측 구간 내 `max(forecast)` + 발생 시점.
  - 임계치 입력은 기존 `calculate_power_risk` 임계 상수([power/services/threshold_eval.py:74](../../../fastapi-server/power/services/threshold_eval.py#L74)) / `GAS_THRESHOLDS`([core/gas_thresholds.py:10](../../../fastapi-server/core/gas_thresholds.py#L10)) 재사용.

### B-4. 가스 ARIMA 추론 경로 연결 (가스 점선 전제)
- 현재 가스는 ARIMA 추론 미연결. 가스 점선이 필요하면:
  - `arima_<gas>.pkl` 로드는 이미 있음([gas_service.py:66](../../../fastapi-server/gas/services/gas_service.py#L66)) → B-1의 series forecast를 가스 윈도우에 적용하는 경로 추가.
  - 또는 **1차 범위에서 가스 점선은 보류**하고 전력만 우선 적용하는 컷도 가능(아래 §6 범위 옵션).

### B-5. (선택) 예측 결과 영속화
- 실시간 표시만이면 불필요(API가 즉석 계산).
- 이력/재현이 필요하면 `MLAnomalyResult.feature_snapshot_json`에 배열 저장 또는 별도 테이블. **1차는 비저장 권장** (단순성 우선).

---

## 4. 추가해야 할 것 — 프론트

### F-1. AI 탭 전용 line 차트 신규
- `switchGasTab('ai')` / `switchTab('ai')`에서 실시간 캐시 재표시 대신 **B-2 API fetch → line 차트 렌더**로 분기.
- 측정 구간 = 실선 dataset, 예측 구간 = 점선 dataset(`borderDash`), 두 dataset를 "지금" 시점에서 연결.

### F-2. 배경 3단계 zone
- `safeBand`([chart-helpers.js:151](../../../drf-server/static/js/shared/chart-helpers.js#L151)) 확장 또는 신규 플러그인: 정상(하단 어두움)/주의(주황)/위험(상단 빨강) 영역을 y축 임계치 경계로 색칠.

### F-3. "지금" 마커 연결
- 기존 `nowMarker`([chart-helpers.js:214](../../../drf-server/static/js/shared/chart-helpers.js#L214)) 플러그인을 AI 차트에 plugins 등록만.

### F-4. 인사이트 배지 + 수직 가이드라인 툴팁
- 배지: 카드 상단 "현재 농도/현재 부하" 텍스트 (현재값은 실시간 캐시 재사용).
- 수직선: 커서 추종 dashed line 플러그인(소량) + Chart.js tooltip 강화.
- 전력 카드에 ETA/예상최대부하 텍스트(B-3 결과) 표시.

### F-5. 공지 배너 처리
- 연동 완료 카드는 "미연동" 배너 비표출 분기.

---

## 5. 작업 분할 표

| # | 작업 | 영역 | 재활용 자산 | 검증 |
|---|---|---|---|---|
| B-1 | multi-step `_arima_forecast` | fastapi `ai/router.py` | 기존 ARIMA pkl/result | 단위테스트: `steps=N` → 길이 N 배열·CI 단조 확장 |
| B-2 | forecast 서빙 API | fastapi `ai/` | `_fetch_active_model_meta`, raw 조회 selector | curl로 측정+예측 구간 JSON 확인 |
| B-3 | ETA·최대부하 헬퍼 | fastapi `ai/` | threshold 상수(`threshold_eval`, `gas_thresholds`) | 단위테스트: 합성 상승 시계열 → 교차 step 정확도 |
| B-4 | 가스 ARIMA 연결(선택) | fastapi `gas/` | `_arima_models` 로드부 | 가스 forecast 응답 유무 |
| F-1 | AI 탭 line 차트 | drf static js | Chart.js, `switchTab` 분기점 | 탭 클릭 시 실선+점선 렌더 육안 |
| F-2 | 3단계 zone | drf chart-helpers | `safeBand`, `CHART_COLOR` | 임계치 경계와 색 경계 일치 |
| F-3 | nowMarker 연결 | drf chart-helpers | `nowMarker`(기존) | "지금" 수직선 위치 |
| F-4 | 배지·수직툴팁·ETA 텍스트 | drf static js | Chart.js tooltip | 호버 동작·ETA 문구 |
| F-5 | 배너 분기 | drf templates/js | — | 연동 카드 배너 제거 |

> 정적파일 변경 반영 절차: 소스 편집만으로는 반영 안 됨. `exec drf collectstatic --noinput` → `restart drf` 필요(WhiteNoise manifest). 템플릿 변경은 `restart drf`만.

---

## 6. 범위 옵션 (의사결정 필요)

| 옵션 | 내용 | 비용 | 비고 |
|---|---|---|---|
| **A. 풀 명세** | 전력+가스 multi-step 점선 + ETA + 예상최대부하 | 큼(B-1~B-4 전부) | 명세 100% |
| **B. 전력 우선** | 전력만 점선+ETA, 가스 점선 보류 | 중 | B-4 생략. 전력이 시연 main course와 정합 |
| **C. 축소판(시연용)** | 점선은 짧은 horizon, ETA 문구 대신 **신뢰구간 밴드** 표시 | 소 | 아래 §7 한계 회피 |

---

## 7. ⚠️ 정직 표기 — 데이터-목표 한계 (포장 금지)

이미 실측·검증된 사실이며, 명세를 **그대로 구현하면 데이터가 약속을 못 받친다**:

- ARIMA 리드타임 실측: predict_warn 선행 19%, median 0.4s로 **작음**. "약 782분 뒤 위험 도달" 같은 **장기 단정 ETA는 1-step/단기 ARIMA로 신뢰도 없음**.
- multi-step으로 horizon을 늘리면 **신뢰구간(CI)이 step마다 급격히 발산** → 점선이 사실상 정보 가치를 잃을 수 있음.
- 따라서 ETA 문구는 **"약 N분 뒤(예측, 신뢰구간 ±)" 형태로 불확실성 동반 표기** 권장. "782분 뒤 위험" 같은 확정 단언은 **과대표기**.
- 근거 메모: `power_ai_leadtime_validation_2026_06_08`, `ai_direct_push_latency_measured_2026_06_08`.

---

## 8. 다음 액션

1. **범위 결정** (§6 A/B/C 중 택1) — 시연 정합성·기간 고려 시 **B(전력 우선)** 또는 **C(축소판)** 권장.
2. 범위 확정 후 B-1 → B-2 → B-3 순으로 백엔드 선행(데이터가 없으면 프론트가 그릴 게 없음), 이어 F-1~F-5.
3. ETA 문구 표기 정책(§7) 먼저 합의 — 구현 후 문구 수정은 재작업 비용.
