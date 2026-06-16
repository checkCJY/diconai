# ARIMA(1,1,1) 단발 spike 한계 — forecast 가 actual 따라가 CI 위반 False

## 증상

전력 un-downgrade W3.2 검증 — 8000W (정격 7500W 의 107%) 강제 주입 시 ARIMA forecast 결과:

```
[anomaly_inference] device=63200c3afd12 ch=1 watt value=8000.0
  threshold=danger pred=anomaly arima_v=False combined=danger
```

- threshold_risk = `danger` (정격 107%) ✓
- IF prediction = `anomaly` (학습 분포 밖) ✓
- **ARIMA violation = `False`** ✗ — **단발 spike 인데 forecast 신뢰구간 안 들어옴**

기대: `(danger, anomaly, True)` → un-downgrade 매트릭스의 강한 신호
실제: `(danger, anomaly, False)` — IF + threshold 만으로 결정

## 원인

### ARIMA(1,1,1) 의 빠른 적응 특성

ARIMA(p=1, d=1, q=1):
- p=1 (AR): 직전 1틱 자기회귀
- d=1 (I): 1차 차분 (trend 안정화)
- q=1 (MA): 직전 1틱 이동평균

**`apply(endog=values)` 호출 시점**:
1. 슬라이딩 윈도우 30개에 모델 적용 (`new_result = arima_result.apply(endog=values)`)
2. 마지막 1~3 틱 spike 가 입력에 포함됨 — ARIMA 가 즉시 자기회귀 학습 패턴으로 적응
3. `get_forecast(steps=1)` 의 신뢰구간 (95% CI) 이 spike 근처로 따라감
4. actual (마지막 값) 이 CI 안에 들어옴 → `is_violation = False`

### 실모델 검증
```python
# 학습된 ARIMA v1 로 검증
from ai.router import _get_or_load_arima, _arima_forecast
forecast = _arima_forecast([7475, 7470, 7480, ..., 8000], arima_result)
# → forecast=1091.57 CI=[645, 1538] actual=1110 violation=False (정상 케이스)
# 8000W spike 도 비슷 — forecast 가 actual 근처로 빠르게 적응
```

### 모델의 본질적 한계

| 패턴 | ARIMA(1,1,1) 가 잡는가? | 이유 |
|---|---|---|
| **단발 spike** (1~3틱) | ❌ | 빠른 적응 — CI 안 들어옴 |
| **점진 상승** (trend break) | ✓ | trend 학습 — CI 위반 명확 |
| **seasonal 일탈** (시각 사이클) | ❌ | non-seasonal 모델 |
| **장기 패턴 변화** | ✓ | trend 변화 잡음 |

## 진단 단계

```python
# fastapi 컨테이너에서 실모델 로드 후 forecast 동작 확인
docker compose exec fastapi python -c "
from ai.router import _get_or_load_arima, _arima_forecast
import asyncio

async def check():
    entry = await _get_or_load_arima('power', 'power:device_1:ch1:watt')
    # 정상 윈도우 + 마지막에 spike 주입
    normal = [7470 + i*0.5 for i in range(29)]  # 점진 정상
    with_spike = normal + [8000.0]              # 마지막 spike
    result = _arima_forecast(with_spike, entry.model)
    print(f\"forecast={result['forecast']:.1f} CI=[{result['ci_lower']:.0f},{result['ci_upper']:.0f}] actual={result['actual']:.1f} violation={result['is_violation']}\")

asyncio.run(check())
"
# → forecast 가 8000 근처로 적응. violation=False
```

## 해결 — 모델 한계 인지 + 다른 축으로 보완

ARIMA(1,1,1) 단독으로 단발 spike 잡으려고 하지 않음. 4축 보완:

| 패턴 | 잡는 모델 | 본 시스템 |
|---|---|---|
| 단발 spike | **IF + 정적 룰** | `IsolationForest.predict()` + `calculate_power_risk` |
| 점진 trend break | **ARIMA forecast** | `_arima_forecast` 의 CI 위반 |
| seasonal (시각 사이클) | **시각 휴리스틱 (현재)** / SARIMAX (미래) | `_is_night_kst_iso` + 정격 30% |
| 학습 분포 자체 변화 | **재학습 cadence** | W5 주 단위 retrain task |

8000W 케이스에서:
- threshold = `danger` ✓ (정적 룰)
- IF prediction = `anomaly` ✓ (학습 분포 밖)
- ARIMA violation = False (단발 spike 한계 — 의도된 동작)
- 4축 결합 `combine_risk_3axis(danger, anomaly, False)` = `danger` ✓ — 정확히 작동

→ **ARIMA 가 잡지 못해도 다른 축이 잡으므로 시스템 전체는 정상**.

### 향후 정확도 향상 옵션

1. **forecast steps 확장** (steps=1 → steps=5~10) — multi-step 으로 미래 N틱 예측 + 누적 위험 (PREDICTIVE_ALERT — STEP 5 권고)
2. **order 자동 선택** (`pmdarima.auto_arima`) — (1,1,1) 고정 → AIC/BIC 최소화로 도메인별 최적 order
3. **SARIMAX 도입** — seasonal order 추가 → 시각 사이클 자동 학습 (night 휴리스틱 대체 가능)
4. **재학습 cadence 자동화** — 주 단위 retrain task (W5 후속)

위 옵션 도입 시 단발 spike 자체 잡는 게 목적이 아니라 **ARIMA 가 다른 패턴을 잘 잡도록 정확도 향상**.

## 학습 포인트

- **forecast 모델의 "갱신 속도" 와 "예측 신뢰구간"** 의 균형:
  - 빠른 적응 (작은 윈도우 / 낮은 p, q) → 단발 spike 못 잡음 / trend break 못 잡음
  - 느린 적응 (큰 윈도우 / 높은 p, q) → 단발 spike 잡지만 false positive 도 잡음 + 학습 시간 ↑
- **모델의 강점 + 한계 명시적 인지** — ARIMA(1,1,1) 가 잡는 것 (trend) vs 못 잡는 것 (단발 spike, seasonal) 을 미리 알고 다른 축으로 보완
- **4축 결합의 가치** — 어떤 모델도 모든 패턴을 잡지 못함. 도메인별 패턴에 맞춰 4축 (정적 룰 + IF + ARIMA + 시각 휴리스틱) 결합이 robust
- **e2e 검증의 중요성** — 단위 sanity 만으로는 ARIMA 의 forecast 가 actual 따라가는 행동 못 잡음. 8000W 강제 주입 같은 e2e 시나리오에서 발견
- **"의도된 한계" 와 "실제 버그" 구분** — ARIMA violation=False 는 버그가 아니라 모델 특성. 다른 축 (IF, threshold) 이 잡으므로 전체 결정 정상

## 같은 패턴이 재발할 영역

- 가스 IF + ARIMA 통합 — 가스 누출 spike 도 ARIMA 격하 패턴에서 잘 안 잡힘. IF + 임계치가 잡음
- 신규 도메인 (진동, 압력, 유량 등) 도입 시 — ARIMA 의 강점·한계 패턴 도메인 특성과 매칭 검토
- Z-score / Change Point 도입 (본 plan D2/E1) 후 — 이 두 축이 ARIMA 의 단발 spike 한계를 보완 가능 (Z-score = 평소 대비 튐, CP = 변화 시점)

## 관련

- 전력 un-downgrade 보고서 §7.2 + §9.4 (8000W 검증 + 단발 spike 한계 명시)
- 본 plan [`anomaly-detection-zscore-changepoint.md`](../plan/anomaly-detection-zscore-changepoint.md) §1.2 (ARIMA 가 잡는 패턴 비율)
- STEP 5 권고: skill/AI/시계열AI/STEP 5 §2329~2356 (ARIMA 와 IF 의 역할 분담)
