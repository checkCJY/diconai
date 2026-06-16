# diconai AI 이상탐지 파이프라인

> 작성: 2026-05-27 · 대상: 백엔드 팀 SoT · 범위: 가스/전력 AI 추론 → 알람 발화

---

## 한 줄 요약

> **IsolationForest + ARIMA + Z-score + ChangePoint** 4종을 결합해 알람을 발화한다.
> 가스는 IF 단독 발화, 전력은 5축 결합 매트릭스 + 야간 격상 + AI/정적 결과 매트릭스를 거친다.

---

## 1. 한눈에 보는 전체 파이프라인

```
┌──────────────────────────────────┬──────────────────────────────┐
│  가스 (1패킷에 10종 가스)        │  전력 (16채널 × watt/cur/vol)│
├──────────────────────────────────┼──────────────────────────────┤
│  1. 임계치 평가                  │  1. Quality Guard            │
│     (10가지 가스 caution/danger) │     (단절/overflow/stuck)    │
│                                  │                              │
│  2. CP 게이트 (ruptures Pelt)    │  2. 윈도우 누적 (30개)       │
│     CP 없으면 IF 스킵            │     부족 → WARMING_UP        │
│                                  │                              │
│  3. IF 다변량 추론               │  3. 5축 추론 (병렬)          │
│     (9종 = 36 or 39피처)         │     · IF                     │
│                                  │     · ARIMA (95% CI 위반)    │
│  4. pred == -1 + rate_limit_ok   │     · Z-score                │
│     → push_alarm                 │     · ChangePoint            │
│                                  │     · threshold              │
│                                  │                              │
│                                  │  4. combine_risk_5axis       │
│                                  │     → combined ∈ {normal,    │
│                                  │        caution, predict_warn,│
│                                  │        warning, danger}      │
│                                  │                              │
│                                  │  5. 야간 격상 (watt + KST)   │
│                                  │                              │
│                                  │  6. decide_alarm             │
│                                  │     (AI state × static)      │
│                                  │     → source 6종 → push      │
└──────────────────────────────────┴──────────────────────────────┘
                              │
                              ▼
              ┌────────────────────────────┐
              │  forward_inference_e2e     │
              │  → DRF MLAnomalyResult     │
              │  → DRF AlarmRecord         │
              │  → WebSocket (push_alarm)  │
              └────────────────────────────┘
```

---

## 2. 가스 파이프라인

**진입점:** [`gas/services/gas_service.py:90`](../../fastapi-server/gas/services/gas_service.py#L90) `process_gas_data`

### 흐름

```
센서 1패킷 (10종 가스: O2, CO, CO2, H2S, LEL, NO2, SO2, O3, NH3, VOC)
   │
   ├─ ① 임계치 평가 (10종 모두)                            ← AI 와 별개, 항상 실행
   │     calculate_individual_risks() → {gas}_risk: normal|warning|danger
   │     → DRF 저장 + DRF Celery 측 정적 룰 알람 트리거
   │
   ├─ ② 9종 윈도우 누적 (deque maxlen=30 × 9, GAS_FIELDS 순서)
   │     ※ lel 제외 — raw_payload 에만 보관, AI 추론 대상 아님
   │
   ├─ ③ ChangePoint 게이트 (ruptures.Pelt model="rbf")
   │     9가스 중 하나라도 변화점 감지 → 통과
   │     모두 안정 → IF 추론 스킵 (CPU 절약)
   │
   ├─ ④ IF 모델 로드
   │     sensor_identifier = "gas:sensor_1:co_h2s_co2_o2_no2_so2_o3_nh3_voc" (고정)
   │     ※ 가스는 모든 센서가 같은 모델 공유 (전력은 채널별 학습)
   │
   ├─ ⑤ 다변량 피처 빌드 (_build_multi_feature_row)
   │     ARIMA pkl 없으면 36피처: 9가스 각 [value, roll_mean, roll_std, diff]
   │     ARIMA pkl 있으면 최대 39피처: 위 + arima_resid (CO/H2S/CO2 한정)
   │
   ├─ ⑥ pred = model.predict(row)[0]     ← 1 정상, -1 이상
   │     score = model.decision_function(row)[0]
   │
   ├─ ⑦ ML 결과는 항상 DRF 저장 (forward_inference_e2e)
   │     pred 가 -1 이든 1 이든 MLAnomalyResult row 1건 생성
   │
   └─ ⑧ pred == -1 AND (now - last_fired >= 30s) 일 때만 발화
         │
         ├─ Redis mute 마킹 × 9가스 (GAS_FIELDS 전부)
         │   · mark_gas_ai_recent  → DRF 정적 룰 60s mute
         │     (단, DRF 측 _AI_GUARDED_GASES={co,h2s,co2}만 mute 적용 → 실효 3종)
         │   · mark_gas_ai_state(FIRED)
         │
         ├─ push_alarm (gas_anomaly_ai, danger)
         │   → WebSocket 큐로 브라우저 실시간 전달
         │
         └─ forward_inference_e2e 의 alarm_payload 동봉
             → DRF AlarmRecord 생성 + 이벤트 저장
```

### 핵심 변수

| 변수 | 값 | 위치 |
|---|---|---|
| 가스 항목 | 9종 (`GAS_FIELDS`: co/h2s/co2/o2/no2/so2/o3/nh3/voc, lel 제외) | [`gas/constants.py`](../../fastapi-server/gas/constants.py) |
| 윈도우 길이 | 30 (1Hz → 30초) × 9종 | [`gas_service.py:95`](../../fastapi-server/gas/services/gas_service.py#L95) `_gas_windows` |
| CP 패널티 (`penalty`) | `DEMO_GAS_CP_PENALTY` 기본 3.0 (env override, 시연 1.0) | [`config.py:75`](../../fastapi-server/core/config.py#L75) |
| CP 커널 | `"rbf"` (ruptures.Pelt) | [`gas_service.py:86`](../../fastapi-server/gas/services/gas_service.py#L86) |
| Rate limit | 30s | [`config.py:90`](../../fastapi-server/core/config.py#L90) `GAS_AI_RATE_LIMIT_SEC` |
| 발화 단위 키 | `gas:{device_id}:co_h2s_co2_o2_no2_so2_o3_nh3_voc` | sensor 1개당 1키 — 9종 묶어서 한 알람 |
| IF 모델 식별자 | `gas:sensor_1:co_h2s_co2_o2_no2_so2_o3_nh3_voc` | [`gas_service.py:149`](../../fastapi-server/gas/services/gas_service.py#L149) (전 센서 공유) |
| ARIMA pkl | `arima_{co,h2s,co2}.pkl` (`ARIMA_GAS_FIELDS` 한정, 존재 시만 적재) | [`gas_service.py:69`](../../fastapi-server/gas/services/gas_service.py#L69) |
| 발화 시 risk_level | `danger` 고정 | [`gas_service.py:244`](../../fastapi-server/gas/services/gas_service.py#L244) |

### 가스 임계치 (정적 룰, AI 와 무관)

[`fastapi-server/core/gas_thresholds.py:14`](../../fastapi-server/core/gas_thresholds.py#L14)

| 가스 | normal (안전) | warning | danger | 비고 |
|---|---|---|---|---|
| **O2** | 18.0~23.5% | <18.0 또는 >23.5 | <16.0 | 낮을수록 위험 (역방향) |
| **CO** | <25 ppm | 25~199 | ≥200 | |
| **H2S** | <10 ppm | 10~14 | ≥15 | |
| **CO2** | <1000 ppm | 1000~4999 | ≥5000 | |
| **NO2** | <3 ppm | 3~4 | ≥5 | |
| **SO2** | <2 ppm | 2~4 | ≥5 | |
| **O3** | <0.06 ppm | 0.06~0.11 | ≥0.12 | |
| **NH3** | <25 ppm | 25~34 | ≥35 | |
| **VOC** | <0.5 ppm | 0.5~0.99 | ≥1.0 | |
| **LEL** | — | — | — | 임계치 미정의, 수집만 |

### 정적 룰 알람 라우팅 (DRF 측, AI 와 병행)

[`drf-server/apps/monitoring/services/gas_alarm.py`](../../drf-server/apps/monitoring/services/gas_alarm.py) `trigger_gas_alarms`

위험도 → Celery 태스크 분기:

| 위험도 | 동작 | 비고 |
|---|---|---|
| **DANGER** | 즉시 `fire_danger_alarm_task.delay()` | |
| **WARNING** | 30초 타이머 (`apply_async(countdown=30)`) | 그 동안 normal 되면 `_revoke()` |
| **NORMAL** | 이전 경보 있으면 정상화 알림 + state clear | |

상태 키 (Redis):
- `alarm:state:{sensor_id}:{gas}` — `normal`/`warning`/`danger`. TTL 60s.
- `alarm:task:{sensor_id}:{gas}` — WARNING 타이머 Celery task ID (revoke용). TTL=35s.

### AI ↔ 정적 룰 분담

| 가스 | AI 추론 | 정적 룰 | Mute 적용 |
|---|---|---|---|
| **CO, H2S, CO2** | ✅ 다변량 IF | ✅ 임계치 | ✅ AI 발화 시 60s mute |
| O2, NO2, SO2, O3, NH3, VOC | ❌ | ✅ 임계치 | ❌ Mute 무관, 즉시 발화 |
| LEL | ❌ | ❌ (임계치 미정의) | — |

`_AI_GUARDED_GASES = {"co", "h2s", "co2"}` ([`gas_alarm.py:25`](../../drf-server/apps/monitoring/services/gas_alarm.py#L25))

### ChangePoint 게이트 동작

```python
# gas_service.py:123-128
cp_detected = (
    _detect_change_point(list(_co_window))
    or _detect_change_point(list(_h2s_window))
    or _detect_change_point(list(_co2_window))
)
if not cp_detected:
    # IF 추론 스킵 — 모든 가스가 안정 상태
    return
# 적어도 한 가스에서 패턴 변화 감지 → IF 진행
```

**왜 게이트?** 9가스가 모두 평탄하면 IF 가 어차피 normal 반환. 매 패킷마다 36~39차원 IF 추론은 CPU 비용. CP 가 cheap pre-filter 역할.

### 다변량 피처 빌드 (36 vs 39)

ARIMA pkl 로드 성공 여부에 따라 피처 차원 변동. 기본 피처는 9가스 × 4 = 36, ARIMA 잔차는 `ARIMA_GAS_FIELDS`(CO/H2S/CO2)에 pkl 이 있을 때만 가스당 1개 추가 → 최대 39.

```
ARIMA pkl 없음 (36피처): GAS_FIELDS(9종) 각 [value, roll_mean, roll_std, diff]
  [CO_value,  CO_roll_mean,  CO_roll_std,  CO_diff,
   H2S_value, H2S_roll_mean, H2S_roll_std, H2S_diff,
   ... (CO2, O2, NO2, SO2, O3, NH3, VOC 동일) ]

ARIMA pkl 있음 (최대 39피처): 위 36 + CO/H2S/CO2 각 arima_resid 1개씩
```

⚠ IF 학습 시 피처 개수와 추론 시 피처 개수가 일치해야 한다 (학습·추론 모두 `GAS_FIELDS` 순서 고정). 운영 모델 피처 개수 = 학습 명령에서 결정.

### 가스만의 특징 (전력과 비교)

- **공통 IF 1개**: 가스는 모든 sensor 가 같은 모델 공유 (`sensor_identifier="gas:sensor_1:co_h2s_co2_o2_no2_so2_o3_nh3_voc"` 고정). 전력은 채널별 학습.
- **ARIMA 사전 로드**: 모듈 import 시점에 CO/H2S/CO2 ARIMA pkl 을 메모리에 로드. 전력은 lazy 로드 (첫 요청 시).
- **5축 결합 미사용**: `combine_risk_5axis` 안 거친다. IF `pred=-1` 이면 무조건 `danger`.
- **AI state 매트릭스 없음**: `decide_alarm` 없음. AI 발화 = 단순 push.
- **CP 가 알람 신호 아님**: 게이트 역할만. 전력에서는 CP 가 직접 발화 신호.

### 발화 페이로드 (예시)

```python
# gas_service.py push_alarm payload (대표 위험 가스 _lead_gas 기준)
{
    "alarm_type": "gas_anomaly_ai",
    "risk_level": "danger",
    "source_label": "가스센서 AI 이상탐지",
    "summary": "가스 이상 감지 (AI) | CO:35 H2S:8 CO2:1200",
    "message": "가스 이상 감지 (AI) | CO:35 H2S:8 CO2:1200",
    "is_new_event": True,
    "gas_type": "co",          # ※ _lead_gas = 위험 가스 중 첫 번째 (없으면 "co")
    "measured_value": 35,      # gas_values[_lead_gas]
}
```

⚠ `gas_type` 결정: 다변량 IF 는 9가스 동시 이상 신호. 알람 UI 는 단일 가스 라벨이 필요해, `individual_risks`에서 warning/danger 인 가스(`_risky`) 중 **첫 번째를 대표(`_lead_gas`)** 로 쓰고 위험 가스가 없으면 `"co"` 로 fallback. `summary` 에는 위험 가스 값을 모두 표기 (`_gas_detail`).

---

## 3. 전력 파이프라인

**진입점:** [`power/services/anomaly_inference.py:166`](../../fastapi-server/power/services/anomaly_inference.py#L166) `process_anomaly_inference`

### 흐름

```
센서 1패킷 ({채널: 값} × watt/current/voltage/onoff)
   │
   채널마다 반복 ↓
   │
   ├─ Quality Guard                          ← 통신단절/overflow/stuck 시 스킵
   │     classify_sensor_status()
   │
   ├─ AI 활성 채널? (ch1/9/14/15 watt만)
   │     비활성 → DISABLED + decide_alarm
   │
   ├─ 윈도우 30개 채웠나?
   │     부족 → WARMING_UP + decide_alarm
   │
   ├─ Stuck 체크 (전 값 동일하면 센서 고장)
   │
   ├─ 5축 추론 (병렬)
   │     · IF       → prediction ∈ {normal, anomaly}
   │     · ARIMA    → arima_violation ∈ {True, False}  (95% CI 밖이면 True)
   │     · Z-score  → z_anomaly ∈ {True, False}        (|z| >= 3.0)
   │     · CP       → change_point ∈ {True, False}     (STABLE→SHIFT 전이)
   │     · threshold → "normal" | "warning" | "danger"
   │
   ├─ combine_risk_5axis(...) → (combined, escalation_source)
   │
   ├─ 야간 격상 (data_type == "watt" + KST 야간 + value > rated × ratio)
   │     → algorithm_source = "night_abnormal"
   │
   ├─ algorithm_source 우선순위 결정
   │     night > combined(IF+ARIMA) > change_point > arima > zscore > IF
   │
   ├─ combined 발화 등급?
   │     YES → rate_limit 체크 (60s)
   │             통과 → FIRED + mark_ai_recent + push
   │             차단 → ML 저장만, push 안 함
   │     NO  → INFERRED_NORMAL
   │
   └─ decide_alarm (AI state × static_risk → source 6종)
         · ai            → power_anomaly_ai
         · static_*      → power_overload (AI 보완)
         · None          → 알람 없음
```

### 핵심 변수

| 변수 | 값 | 위치 |
|---|---|---|
| 윈도우 (IF/Z 공통) | 30 | [`zscore_anomaly.py:14`](../../fastapi-server/power/services/zscore_anomaly.py#L14) |
| 윈도우 (CP) | 60 (=2×30) | [`change_point_service.py:28`](../../fastapi-server/power/services/change_point_service.py#L28) |
| AI 활성 채널 | ch1, 9, 14, 15 (watt만) | [`anomaly_inference.py:80-85`](../../fastapi-server/power/services/anomaly_inference.py#L80-L85) |
| Z 임계 | 3.0σ | [`anomaly_inference.py:287`](../../fastapi-server/power/services/anomaly_inference.py#L287) |
| CP 평균 변화 | `_MEAN_K = 3.0` | [`change_point_service.py:29`](../../fastapi-server/power/services/change_point_service.py#L29) |
| CP 분산 변화 | `_STD_K = 2.0` | [`change_point_service.py:30`](../../fastapi-server/power/services/change_point_service.py#L30) |
| ARIMA 신뢰구간 | 95% (alpha=0.05) | [`ai/router.py:277`](../../fastapi-server/ai/router.py#L277) |
| Rate limit | 60s | [`anomaly_inference.py:90`](../../fastapi-server/power/services/anomaly_inference.py#L90) |

---

## 4. 탐지기 4종 상세

### 4-1. IsolationForest

**역할:** 복합 패턴 이상 탐지 (값 + 평균 + 표준편차 + 변화율 종합)

**전력 (단변량, 4피처):**
```python
# ai/router.py:245
arr = window_values[-30:]
features = [
    arr[-1],            # value
    arr.mean(),         # roll_mean
    arr.std(ddof=0),    # roll_std
    arr[-1] - arr[-2],  # diff
]
```

**가스 (다변량, 36 또는 최대 39피처):**
```python
# ai/router.py _build_multi_feature_row
# GAS_FIELDS(9종)별 4피처 + (선택) CO/H2S/CO2 ARIMA 잔차
# → 4×9 = 36피처, ARIMA pkl 있으면 +3 = 최대 39피처
```

**판정:** `model.predict(row)[0]` → `1` 정상, `-1` 이상

---

### 4-2. ARIMA

**역할:** 미래값 예측. 도메인마다 사용법 다름.

**전력 — 1-step ahead forecast + 95% CI 위반:**
```python
# ai/router.py:299
new_result = arima_result.apply(endog=values[:-1])   # ⚠ 마지막 값 제외하고 학습
forecast = new_result.get_forecast(steps=1)
ci_lower, ci_upper = forecast.conf_int(alpha=0.05)[0]
actual = values[-1]
arima_violation = actual < ci_lower or actual > ci_upper
```

> `values[:-1]` 로 학습하는 이유: 학습에 actual 이 포함되면 예측이 actual 근처로 따라가 false negative 가 생긴다.

**가스 — 잔차를 IF 피처로 주입:**
```python
# ai/router.py:266
new_result = arima_result.apply(endog=values)
resid = float(new_result.resid[-1])
# → 36피처 IF 에 CO/H2S/CO2 잔차 추가 시 최대 39피처 IF
```

---

### 4-3. Z-score (전력만)

**역할:** 단발 급등 탐지 (윈도우 평균에서 얼마나 벗어났나)

```python
# zscore_anomaly.py:21
mean = np.array(window).mean()
std  = np.array(window).std()
z    = abs(value - mean) / (std + 1e-9)   # std=0 분모 폭발 방지
return bool(z >= 3.0), float(z)
```

---

### 4-4. ChangePoint

**전력 (two-window, [`change_point_service.py`](../../fastapi-server/power/services/change_point_service.py)):**

```python
# 60개 윈도우를 30+30 으로 분할
prev = arr[:30]
curr = arr[30:60]

mean_shift = |curr.mean - prev.mean| / (prev.std + ε)
std_ratio  = (curr.std + ε) / (prev.std + ε)

is_change = (mean_shift >= 3.0) OR (std_ratio >= 2.0) OR (std_ratio <= 0.5)

# 상태 머신: STABLE → SHIFT 전이 시점만 True
#           SHIFT 지속 중에는 False (중복 발화 방지)
```

**가스 (ruptures Pelt, [`gas_service.py:63`](../../fastapi-server/gas/services/gas_service.py#L63)):**

```python
model = rpt.Pelt(model="rbf").fit(arr)
result = model.predict(pen=3.0)
return len(actual_cps) > 0
```

> 가스는 알람 신호가 아니라 **IF 추론 트리거 게이트**. CP 안 잡히면 IF 자체를 안 돌린다.

---

## 5. 5축 결합 매트릭스

**위치:** [`ai/risk_combine.py`](../../fastapi-server/ai/risk_combine.py) (3개 함수: 2축 → 3축 → 5축)

### 2축 — `combine_risk()` (가장 단순한 기본)

| threshold ↓ \\ IF → | normal | anomaly |
|---|---|---|
| **normal** | normal | predict_warn |
| **warning** | caution | **danger** |
| **danger** | danger | danger |

### 3축 — `combine_risk_3axis()` (+ ARIMA)

핵심 차이: **두 AI (IF + ARIMA) 동의 시 한 단계 격상.** 단독 발화는 보수적.

| threshold | IF | ARIMA | combined |
|---|---|---|---|
| normal | normal | True | predict_warn |
| normal | anomaly | False | predict_warn |
| normal | anomaly | True | **warning** ↑ |
| warning | anomaly | False | warning |
| warning | anomaly | True | **danger** ↑ |
| danger | * | * | danger |

### 5축 — `combine_risk_5axis()` (+ Z-score + CP, 전력 전용)

```python
# 1단계: 3축 결과 (threshold + IF + ARIMA) 가 base
base = combine_risk_3axis(threshold_risk, if_prediction, arima_violation)

# 2단계: base 가 normal 이 아니면 Z/CP 무시
if base != "normal":
    return base, ""

# 3단계: base 가 normal 이면 Z/CP 가 격상 가능
if change_point:
    return "predict_warn", "change_point"
if z_score_anomaly:
    return "predict_warn", "zscore"
return "normal", ""
```

> **왜 base 발화 시 Z/CP 무시?** ML/threshold 가 이미 강한 신호. Z/CP 는 약한 조기 경고용. 우선순위 명확히 (CRITICAL > ML_ANOMALY > ANOMALY_WARNING > TREND_SHIFT > NORMAL).

---

## 6. AI 상태 × 정적 결과 매트릭스 (전력 전용)

**위치:** [`power/services/decide_alarm.py:58`](../../fastapi-server/power/services/decide_alarm.py#L58)

```
                        정적 결과
                  ┌─────────────┬─────────────┐
                  │  not fired  │   fired     │
   ┌──────────────┼─────────────┼─────────────┤
   │ FIRED        │     ai      │     ai      │  → power_anomaly_ai
   ├──────────────┼─────────────┼─────────────┤
   │ INFERRED_    │   (none)    │ static_     │  → power_overload
   │   NORMAL     │             │ cover_miss  │
   ├──────────────┼─────────────┼─────────────┤
   │ INFERRED_    │   (none)    │ static_     │  → power_overload
   │   FAILED     │             │ cover_inf_  │
   │              │             │ fail        │
   ├──────────────┼─────────────┼─────────────┤
   │ WARMING_UP   │   (none)    │ static_     │  → power_overload
   │              │             │ cover_warmup│
   ├──────────────┼─────────────┼─────────────┤
   │ DISABLED     │   (none)    │ static_no_  │  → power_overload
   │              │             │ ai_available│
   ├──────────────┼─────────────┼─────────────┤
   │ None (장애)  │   (none)    │ static_no_  │  → fail-safe
   │              │             │ ai_available│
   └──────────────┴─────────────┴─────────────┘
```

**핵심:**
- AI 가 발화하면 (`FIRED`) → 정적 결과 무시하고 `ai` source
- AI 가 정상이면 → 정적 결과 만으로 발화하되 source 라벨로 "AI 가 놓침" 명시
- 가스에는 이 매트릭스 없음 (가스는 단순 IF 단독 발화)

---

## 7. AI ↔ 정적 룰 충돌 방지 (Redis Mute)

**문제:** AI 가 발화한 채널에 정적 룰도 같은 시각에 발화하면 알람 중복.

**해결:** AI 가 발화하면 Redis 에 마킹 → 정적 룰이 60초 동안 같은 채널 발화 억제.

### 동작 흐름

```
[t=0s]  AI 가 "warning" 발화
          ↓
        Redis SET (TTL=60s)
          ai_fired:device_1:ch3:normal   = "1"   ┐ level "이하"
          ai_fired:device_1:ch3:warning  = "1"   ┘ 모두 set
          ai_fired:device_1:ch3:danger   = ❌    ← set 안 함

[t=10s] 정적 룰이 같은 채널에 "warning" 발화 시도
          ↓
        is_ai_mute_active("warning") → True
          ↓
        SKIP (중복 방지)

[t=10s] 정적 룰이 같은 채널에 "danger" 발화 시도
          ↓
        is_ai_mute_active("danger") → False  (키 없음)
          ↓
        PASS (격상은 통과)
```

**핵심 설계:**
- AI 발화 level **이하** 키만 set → 더 높은 level (격상) 룰은 자동 bypass
- Redis 장애 시 `False` 반환 (fail-open) — mute 가드 실패가 알람을 막으면 안 됨
- 가스는 별도 prefix: `ai_fired_gas:{sensor_id}:{gas_type}:{rule_level}` (CO/H2S/CO2만 적용)

| 변수 | 값 | 위치 |
|---|---|---|
| `AI_MUTE_TTL_SEC` | 60 | [`alarm_dedupe.py:79`](../../drf-server/apps/alerts/services/alarm_dedupe.py#L79) |
| 전력 키 | `ai_fired:{device_id}:{channel}:{level}` | — |
| 가스 키 | `ai_fired_gas:{sensor_id}:{gas_type}:{level}` | — |

---

## 8. 알람 타입 & 운영자 워딩

### 알람 타입 (DB 저장값)

| alarm_type | 발화 경로 |
|---|---|
| `gas_anomaly_ai` | 가스 IF `pred=-1` + rate limit ok |
| `power_anomaly_ai` | 전력 AI FIRED |
| `power_overload` | 전력 정적 cover (AI miss/warmup/disabled/failed) |
| `gas_threshold` | 가스 정적 임계치 (AI mute 미적용 가스) |

### algorithm_source → 운영자 워딩 (전력 전용)

[`anomaly_inference.py:94-101`](../../fastapi-server/power/services/anomaly_inference.py#L94-L101)

| 코드 | 운영자에게 보이는 워딩 |
|---|---|
| `isolation_forest` | "이상 수치 탐지" |
| `arima` | "이상 패턴 탐지" |
| `combined` | "이상 수치·패턴 동시 탐지" |
| `zscore` | "통계 이상 수치" |
| `change_point` | "패턴 변화 탐지" |
| `night_abnormal` | "야간 이상 가동" |

---

## 9. DB 모델

### MLModel — 학습된 모델 메타

**위치:** [`drf-server/apps/ml/models/ml_model.py`](../../drf-server/apps/ml/models/ml_model.py)

```python
MLModel
├─ sensor_type        : "power" | "gas"
├─ algorithm          : "isolation_forest" | "arima"
├─ sensor_identifier  : "power:device_1:ch3:watt" (또는 "")
├─ version            : 1, 2, 3, ...
├─ file_path          : .pkl 상대경로
├─ feature_columns    : 학습 피처 이름 리스트
├─ params_json        : contamination, n_estimators, ...
└─ is_active          : 활성 모델 1건/매칭단위
```

### MLAnomalyResult — 추론 결과 (1추론 = 1행)

**위치:** [`drf-server/apps/ml/models/ml_anomaly_result.py`](../../drf-server/apps/ml/models/ml_anomaly_result.py)

```python
MLAnomalyResult
├─ ml_model                : FK(MLModel, SET_NULL)
├─ model_version_snapshot  : 모델 삭제돼도 보존
├─ sensor_identifier       : "power:device_1:ch3:watt"
├─ measured_at             : 측정 시각
├─ anomaly_score           : decision_function 결과
├─ prediction              : "normal" | "anomaly"
├─ risk_classified         : "normal" | "caution" | "predict_warn" | "warning" | "danger"
└─ feature_snapshot_json   : 입력 피처 (디버깅용)
```

### AlarmRecord 와의 관계

[`drf-server/apps/alerts/models/alarm_record.py:77`](../../drf-server/apps/alerts/models/alarm_record.py#L77)

- `AlarmRecord.ml_anomaly_result` 가 FK 로 `MLAnomalyResult` 참조
- 1 추론 → N 알람 (같은 추론이 여러 알람 트리거 가능)
- AI 알람만 채움. 정적 룰 알람은 NULL

---

## 10. 캐시 & 모델 동기화

```
[학습]                              [추론]
drf-server                          fastapi-server
   │                                   │
   ├─ train_anomaly_model              ├─ ai/router.py
   ├─ .pkl 저장 (ML_MODELS_DIR)         │   _cache 키 = (sensor_type,
   ├─ MLModel.is_active = True         │              algorithm,
   │                                   │              sensor_identifier)
   │                                   │
   docker named volume 으로 공유 ───────┤   캐시 미스 시
                                       │   → GET /api/ml/models/active/
                                       │   → joblib.load(file_path)
                                       │
                                       └─ TTL 만료 또는 reload 호출 시
                                          캐시 evict → 다시 로드
```

- **캐시 TTL:** `ML_MODEL_CACHE_TTL_SEC` (env). 0 = 무제한.
- **모델 미등록(404) 캐시:** 60s — 데이터마다 DRF 안 찌르려고.
- **수동 reload:** `POST /ai/reload?sensor_type=...&algorithm=...` — 학습 직후 운영자가 호출.

---

## 11. Prometheus 메트릭

운영 중 알람 분포·성능 추적용.

| 메트릭 | 의미 |
|---|---|
| `AI_INFERENCE_DURATION` | 추론 latency (labels: `gas_if`, `power_if`) |
| `AI_INFERENCE_FAILED_TOTAL` | 실패 카운터 (model_not_loaded, inference_error) |
| `AI_BROADCAST_LATENCY` | ingress → push 까지 E2E latency |
| `POWER_AI_COMBINED_TOTAL` | combined_risk 분포 |
| `POWER_AI_AXIS_FIRED_TOTAL` | 5축 발화 기여 (if/arima/zscore/change_point/night) |
| `POWER_AI_ALARM_FIRED_TOTAL` | algorithm_source 별 push |
| `POWER_AI_RATE_LIMITED_TOTAL` | rate limit 차단 횟수 |
| `RULE_FIRE_SUPPRESSED_BY_AI_TOTAL` | AI mute 로 억제된 정적 룰 |

---

## 12. 작업 시 봐야 할 파일 (요약)

| 작업 | 파일 |
|---|---|
| 가스 AI 흐름 | [`gas/services/gas_service.py`](../../fastapi-server/gas/services/gas_service.py) |
| 전력 AI 흐름 | [`power/services/anomaly_inference.py`](../../fastapi-server/power/services/anomaly_inference.py) |
| 모델 로드·캐시 | [`ai/router.py`](../../fastapi-server/ai/router.py) |
| 결합 매트릭스 | [`ai/risk_combine.py`](../../fastapi-server/ai/risk_combine.py) |
| AI state × 정적 분기 | [`power/services/decide_alarm.py`](../../fastapi-server/power/services/decide_alarm.py) |
| Z-score | [`power/services/zscore_anomaly.py`](../../fastapi-server/power/services/zscore_anomaly.py) |
| ChangePoint (전력) | [`power/services/change_point_service.py`](../../fastapi-server/power/services/change_point_service.py) |
| AI Mute (DRF) | [`drf-server/apps/alerts/services/alarm_dedupe.py`](../../drf-server/apps/alerts/services/alarm_dedupe.py) |
| AI Mute (fastapi) | [`fastapi-server/services/ai_mute.py`](../../fastapi-server/services/ai_mute.py) |
| 학습 명령 (IF) | [`drf-server/apps/ml/management/commands/train_anomaly_model.py`](../../drf-server/apps/ml/management/commands/train_anomaly_model.py) |
| 학습 명령 (ARIMA) | [`drf-server/apps/ml/management/commands/train_arima_power_model.py`](../../drf-server/apps/ml/management/commands/train_arima_power_model.py) |

---

## 변경 이력

| 일자 | 변경 |
|---|---|
| 2026-05-27 | 최초 작성 — 실제 코드 기준 SoT |
