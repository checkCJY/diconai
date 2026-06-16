# 전력 AI 종합문서 — 의사결정·적용 현황·한계·로드맵

> **작성일**: 2026-05-21
> **목적**: 전력 AI 작업 (2026-05-08 ~ 2026-05-21) 동안 흩어져 있던 의사결정·적용 현황·한계 문서를 한 장으로 통합. **"왜 이렇게 구현했는가" + "어떤 옵션을 비교해 선택했는가"** 가 핵심.
> **위치**: 본 문서가 향후 SoT (Single Source of Truth). 기존 14+ 개 문서는 보존되어 참조 자산으로 유지 — [부록 B](#부록-b-관련-문서-인덱스) 인덱스 참조.

---

## 0. 한 줄 요약

> **전력 AI = 5축 정책 엔진 (Threshold + IF + ARIMA + Z-score + Change Point) + 시각 컨텍스트 휴리스틱 (night_abnormal) + 정적 안전망 (decide_alarm 6 매트릭스). 가스 (격하) 와는 도메인 의존 architecture 비대칭.**

### 0.1 가스 vs 전력 한눈 비교

| 항목 | 가스 | 전력 |
|---|---|---|
| AI 모델 | IF 단독 (15피처 다변량, ARIMA 잔차는 IF 입력 피처) | **IF + ARIMA 독립 호출** (각 단변량) |
| ARIMA 위치 | 격하 (IF 피처 공급원) | **un-downgrade (동급 algorithm)** |
| 결합 방식 | 2축 (threshold × IF) | **5축 (threshold × IF × ARIMA × Z × CP)** |
| 위험도 등급 | 4단계 (normal/caution/warning/danger) | **5단계 + night_abnormal 격상** |
| 알람 결정 | rate-limit + IF fire | **decide_alarm 6 매트릭스 (AI + 정적 동기)** |
| 시각 분기 | 없음 | **KST 야간 (22~05) + 정격 30% 휴리스틱** |
| 학습 단위 | sensor_type (`gas`) 1개 | **sensor_identifier (`power:device_{mac}:chN:watt`) 채널별** |
| 활성 채널 | CO/H2S/CO2 3가스 | **ch1/9/14/15 watt 4채널 (PoC)** |

### 0.2 데이터 흐름 큰 그림

```
[dummy 또는 IoT]                          [fastapi-server :8001]                                          [drf-server :8000]
                       ┌─────────────────────────────────────────────────────────────┐
POST /api/power/       │  router (수신) → service (윈도우 누적 + AI 추론)             │  → /api/ml/anomaly-results/   (MLAnomalyResult)
  ├ onoff              │     ↓                                                        │  → /api/monitoring/power/data/ (PowerData raw)
  ├ current            │  websocket.state.power_latest (공유 메모리)                  │  → /api/monitoring/power/event/ (AlarmRecord)
  ├ voltage            │     ↓                                                        │
  └ watt   ─AI 추론─►  │  Redis diconai:ws:alarms  →  broadcast_loop (1초 주기)       │
                       └─────────────────────┬───────────────────────────────────────┘
                                             ▼
                                       [브라우저 WS 클라이언트]
```

**핵심 의사결정 결과**: 4가지 측정 종류 (watt/current/voltage/onoff) 중 **`watt` 만 AI 추론 분기 진입**. 나머지는 raw 저장 + 상태 갱신만 ([§6](#6-watt-단독-추론--av-미추론) 근거).

---

## 1. 도메인 의사결정 — 가스 vs 전력 ★

> 본 장이 모든 후속 결정의 출발점. 한 번 정해지면 4 영역 (명령어·DB·코드 흐름·운영) 모두에 파급.

### 1.1 핵심 갈래 — 격하 vs un-downgrade

ARIMA 를 어떻게 활용할지에 두 경로:

| 경로 | 정의 | 가스 채택 | 전력 채택 |
|---|---|---|---|
| **격하 (downgrade)** | ARIMA 잔차를 IF 입력 피처로 흡수. ARIMA 는 독립 algorithm 이 아니라 IF 의 추가 피처 공급원 | ✅ | ❌ |
| **un-downgrade** | ARIMA 를 IF 와 동급 algorithm 으로 분리. forecast + 95% 신뢰구간 위반 여부를 독립 판단자로 사용 | ❌ | ✅ |

### 1.2 ARIMA의 4가지 본질 가치

ARIMA 가 단순 잔차 공급원 이상으로 가져다주는 가치:

| 본질 가치 | 의미 | 운영 시나리오 |
|---|---|---|
| 신뢰구간 위반 | "정상 범위 밖" 의 통계적 의미 명확 | "정상 범위 내 미세 일탈" 조기 인지 |
| Trend break | 점진 상승·하강의 시점 명시 | 모터 부하 점진 증가 (베어링 마모 초기) |
| Multi-step forecast | 1시간 후 예측 + 신뢰구간 | "곧 임계치 도달" 선행 경보 |
| Seasonal | 시간대별 베이스라인 자동 학습 | 주간 vs 야간 가동 패턴 차이 |

**격하 경로** 는 4가지 가치를 모두 잃고 잔차 크기만 살림. → 도메인이 4가지 가치 모두 필요 없을 때만 정당화 가능.

### 1.3 도메인별 필요성 매트릭스

#### 가스 도메인 — 격하 적합

| 가스 이상 패턴 | 빈도 | ARIMA 특수 가치 필요? |
|---|---|---|
| 갑작스러운 CO 농도 ↑ (누출) | 다수 | ❌ 잔차 크면 IF 가 즉시 잡음 |
| 점진적 O2 감소 (밀폐 환경) | 일부 | ⚠️ ramp_up dummy 시나리오로 학습 가능 |
| 야간/주간 베이스라인 변화 | 거의 없음 | ❌ 가스 농도는 시간 의존성 약함 |
| 1시간 앞 forecast 일탈 | 거의 없음 | ❌ 가스 사고는 분 단위 사건 |

→ 가스는 "즉시 위험 / 즉시 알람" 본질. ARIMA forecast·신뢰구간·seasonal 가치 대부분 도메인에서 불필요 → **격하 정당**.

#### 전력 도메인 — un-downgrade 필수

| 전력 이상 패턴 | 빈도 | ARIMA 특수 가치 필요? |
|---|---|---|
| 갑작스러운 부하 ↑ (단락) | 일부 | ❌ 잔차로 잡힘 |
| 모터 부하 점진 증가 (베어링 마모 초기) | 다수 | ✅ **누적 trend break — ARIMA 강점** |
| 시간대별 베이스라인 (주간 1500W vs 야간 200W) | 항상 | ✅ **seasonal — ARIMA 강점** |
| 1시간 앞 forecast 일탈 (선행 경보) | 다수 | ✅ **multi-step forecast — ARIMA 강점** |
| "곧 임계치 도달" 조기 경보 | **핵심 가치 제안** | ✅ **신뢰구간 위반 — ARIMA 본질** |

→ 전력은 **격하 시 사라지는 4가지 가치가 모두 비즈니스 핵심**. 특히 "예측 정비 (Predictive Maintenance)" 비즈니스 framing 자체가 ARIMA forecast + 신뢰구간 위에 서있음 → 격하 시 무력화.

### 1.4 격하 경로의 trade-off

| 보존되는 가치 | 손실되는 가치 |
|---|---|
| ✅ 잔차 크기 (스파이크형 이상 감지) | ❌ 신뢰구간 위반 판정 (정상 범위 내 미세 일탈) |
| ✅ IF 기존 파이프라인 재사용 | ❌ 점진적 trend break (누적 신호) |
| ✅ MLModel/router/AlarmType 무변경 | ❌ multi-step forecast (선행 경보) |
| ✅ Dedup 단순 (1 알람) | ❌ seasonal time-of-day 적응 |
| ✅ 시연 일정 영향 0 | ❌ 운영자 해석력 ("AI score -0.23" only) |

### 1.5 결론 매트릭스

| 도메인 | 사고 시간 척도 | ARIMA 도메인 필요성 | 격하 적합성 | 채택 |
|---|---|---|---|---|
| 가스 | 분 단위 즉시 위험 | 낮음 | ✅ 적합 | **격하** |
| 전력 | 시간~일 단위 점진 변화 | 높음 | ❌ 부적합 | **un-downgrade** |

> 가스 격하는 도메인에 맞춘 최적화이지 일반 해결책이 아님. 전력에 그대로 가져오면 ARIMA 가 잡으려던 가치 대부분을 잃음. **도메인 의존 architecture 비대칭은 의도된 설계 결정.**

### 1.6 후속 영향 — 4 영역 모두에 파급

| 영역 | 가스 (격하) | 전력 (un-downgrade) |
|---|---|---|
| **명령어** | `train_arima_model --gas-names co,h2s,co2` 1개로 일괄 학습 | `train_arima_power_model --device-id N --channel N --data-type watt` 채널별 학습 |
| **DB** | ARIMA pkl 만 (MLModel row 없음, 모듈 import 시 joblib 직접 로드) | ARIMA 도 MLModel row (algorithm='arima', sensor_identifier='power:device_{mac}:chN:watt') |
| **코드 흐름** | `_build_multi_feature_row(arima_results=...)` 한 단계 | quality_guard → IF → ARIMA → 5축 combine → 야간 분기 → algorithm_source 결정 6단계 |
| **운영** | "어떤 알고리즘이 발화" 추적 X | `AlarmRecord.algorithm_source` 라벨링 → 운영자가 추적 가능 |

**참조**: [skill/study/ai-model-study-2026-05-17.md §2.4](ai-model-study-2026-05-17.md), [skill/study/IF_ARIMA_팀공유.md Part 4](IF_ARIMA_팀공유.md), [memory: power-ai-architecture-decision-2026-05-18](../../../../.claude/projects/-home-cjy-diconai/memory/power_ai_architecture_decision_2026_05_18.md).

---

## 2. 5축 정책 엔진 — STEP 5 권고 단계별 도입

### 2.1 STEP 5 권고 매트릭스

학습 자료 [STEP 5 — 디코나이 AI 기반 위험 예측 개발 로드맵](../STEP%205%20—%20디코나이%20AI%20기반%20위험%20예측%20개발%20로드맵.md) 가 제시한 5단계 위험 우선순위:

| 우선순위 | 상태 | 의미 | 적용 축 |
|---|---|---|---|
| 1 | **CRITICAL** | Threshold 초과 (절대 위험) | STEP B (Threshold) |
| 2 | **ML_ANOMALY** | IF anomaly (학습 분포 밖) | STEP F (Isolation Forest) |
| 3 | **ANOMALY_WARNING** | Z-score 임계 초과 (평소 대비 튐) | STEP D (Z-score) |
| 4 | **TREND_SHIFT** | Change Point 감지 (상태 변화 시작) | STEP E (Change Point) |
| 5 | **PREDICTIVE_ALERT** | ARIMA forecast 미래 위험 가능성 | STEP G (ARIMA) |
| 6 | **NORMAL** | 특별한 이상 없음 | (전 축 normal) |

### 2.2 각 축의 책임 분담 — 잡는 이상 패턴

| 축 | 잡는 패턴 | 못 잡는 패턴 | 보완 축 |
|---|---|---|---|
| **Threshold** | 절대값 초과 (정격 100%) | 임계치 직전 조기 경고 | Z-score (3축) |
| **IF** | 학습 분포 밖 (point anomaly + 4피처) | 시간 의존성 (contextual anomaly) | ARIMA (5축) |
| **ARIMA** | trend break / 점진 drift / 시간대 베이스라인 | 단발 spike (빠른 적응으로 CI 따라감) | IF (2축) + threshold (1축) |
| **Z-score** | 통계 spike (3σ 초과) | trend break 시점 | CP (4축) |
| **CP** | 패턴 변화 시점 (STABLE→SHIFT 전이) | 단발 spike, 절대값 위험 | IF (2축) + threshold (1축) |

> **5축 직교성**: 어떤 모델도 모든 패턴을 잡지 못함. 도메인별 패턴에 맞춰 5축 결합이 robust.

### 2.3 STEP B — Threshold (정적 임계치)

**현재 상태**: ✅ 완전 적용.

- 위치: [fastapi-server/power/services/threshold_eval.py](../../fastapi-server/power/services/threshold_eval.py) `calculate_power_risk`
- 단일 진실 공급원: DRF `FacilityThreshold` (정격 % 기반 — warning 80%, danger 100%)
- fastapi 측은 [threshold_sync.py](../../fastapi-server/power/services/threshold_sync.py) 가 DRF threshold-meta 캐시 sync
- **모든 채널이 정적 평가는 받음** — AI 가 침묵해도 정적 안전망은 동작 ([§4.3](#43-decide_alarm-6-매트릭스))

### 2.4 STEP F — Isolation Forest

**현재 상태**: ✅ 완전 적용 (전력 = 4피처 단변량 / 가스 = 15피처 다변량).

#### 2.4.1 4피처 선택 근거

```python
arr = window_values[-30:]  # window=30 틱
value     = arr[-1]                    # 현재값
roll_mean = arr.mean()                 # 이동 평균
roll_std  = arr.std(ddof=0)            # 이동 표준편차
diff      = arr[-1] - arr[-2]          # 1차 차분
```

| feature | 잡는 이상 패턴 |
|---|---|
| `value` | 학습 분포 밖의 큰 값 — 갑자기 매우 높은 전력 |
| `roll_mean` | 점진적 상승·하강 trend — 모터 부하 증가 |
| `roll_std` | 변동 폭 증가 — 베어링 마모, 회로 노이즈 |
| `diff` | 단발 spike — 전력 surge |

**위치 + 분산 + 변화율** — 시간 시계열 기본 통계 요약. IF 가 본질적으로 시간 의존성을 못 보지만, rolling 통계량으로 contextual 신호 일부 흡수.

#### 2.4.2 univariate (전력) vs multivariate (가스)

| 항목 | 전력 | 가스 |
|---|---|---|
| 입력 차원 | 1D univariate (단일 채널 watt) | 3D multivariate (CO + H2S + CO2) |
| feature 수 | 4 | 15 (3 가스 × 5피처) |
| 모델 input shape | (1, 4) | (1, 15) |
| feature builder | `_build_feature_row` | `_build_multi_feature_row(arima_results=...)` |

**가스가 multivariate 인 이유**: 단일 가스만 보면 환기·날씨 같은 자연 변동을 이상으로 오인. CO+H2S+CO2 의 **동시 패턴** 이 진짜 이상 신호 — 산업 안전 도메인 표준.

**전력이 univariate 인 이유**: 채널 간 부하는 독립적 (압연기 vs 공조 vs 조명) — 다변량으로 묶으면 한 채널 정상 패턴이 다른 채널에 끌려감.

#### 2.4.3 IF feature 풍부화 미적용 (단점)

[IF_ARIMA_팀공유 문제 #3](IF_ARIMA_팀공유.md) 가 권고한 추가 feature 중 미적용:
- `hour_of_day` / `day_of_week` (시간 컨텍스트)
- 잔차의 자기상관 (collective anomaly)

→ 시연 후 sprint 의 정확도 본격 개선 과제 ([§12](#12-후속-로드맵)).

### 2.5 STEP G — ARIMA (un-downgrade)

**현재 상태**: ✅ 완전 적용 (전력 = CI 위반 독립 판단자).

#### 2.5.1 1-step forecast + 95% CI

```python
entry_arima = await _get_or_load_arima("power", sensor_identifier)
arima_result = _arima_forecast(list(win), entry_arima.model)
# get_forecast(steps=1) + conf_int(alpha=0.05)
arima_violation = bool(arima_result["is_violation"])
```

[ai/router.py `_arima_forecast`](../../fastapi-server/ai/router.py) — 직전 1틱 자기회귀 (p=1) + 1차 차분 (d=1) + 직전 1틱 이동평균 (q=1).

#### 2.5.2 ARIMA(1,1,1) 의도된 한계

ARIMA 가 잡는 것·못 잡는 것 명시적 인지:

| 패턴 | ARIMA(1,1,1) 가 잡는가? | 이유 |
|---|---|---|
| **단발 spike** (1~3틱) | ❌ | 빠른 적응 — CI 안 들어옴 |
| **점진 상승** (trend break) | ✓ | trend 학습 — CI 위반 명확 |
| **seasonal 일탈** (시각 사이클) | ❌ | non-seasonal 모델 |
| **장기 패턴 변화** | ✓ | trend 변화 잡음 |

**해결 — 4축 보완**: ARIMA(1,1,1) 단독으로 단발 spike 잡으려고 하지 않음.

| 패턴 | 잡는 모델 | 본 시스템 |
|---|---|---|
| 단발 spike | **IF + 정적 룰** | `IsolationForest.predict()` + `calculate_power_risk` |
| 점진 trend break | **ARIMA forecast** | `_arima_forecast` 의 CI 위반 |
| seasonal (시각 사이클) | **시각 휴리스틱 (현재)** / SARIMAX (미래) | `_is_night_kst_iso` + 정격 30% |
| 학습 분포 자체 변화 | **재학습 cadence** | 주 단위 retrain task |

→ **"의도된 한계" 와 "실제 버그" 구분** — ARIMA violation=False 는 버그가 아니라 모델 특성. 다른 축 (IF, threshold) 이 잡으므로 전체 결정 정상.

**참조**: [skill/troubleshooting/0519_arima-single-spike-limit.md](../troubleshooting/0519_arima-single-spike-limit.md) — 8000W 강제 주입 검증 케이스.

### 2.6 STEP D — Z-score 도입 결정 (2026-05-19)

#### 2.6.1 도입 배경

[`docs/codereviews/2026_05_17/alarm-d-option-flow.md`](../../docs/codereviews/2026_05_17/alarm-d-option-flow.md) 시점까지 명시적 결정 흔적 없이 우선순위에서 밀렸음. 추정 사유:
1. IF 입력 피처 (`roll_mean_30`/`roll_std_30`/`diff`) 가 Z-score 효과를 일부 내재 흡수
2. ARIMA (CI 위반) 가 부분 흡수
3. 산업 안전 도메인 — 임계치 자체가 명확하면 Z-score 조기 경고 운영 가치 ↓
4. 학습 시연 D-29 — IF + ARIMA 시연 가치 우선

#### 2.6.2 도입 가치

| 항목 | 운영 가치 | 학습 시연 가치 |
|---|---|---|
| **Z-score (ANOMALY_WARNING)** | 임계치 직전 조기 경고. 운영자가 발화 전 인지 → 사전 대응 가능 | STEP 5 권고 2순위 위험 명시 |

#### 2.6.3 도메인별 적용

| 도메인 | 적용 여부 | 이유 |
|---|---|---|
| 가스 | ✅ 적용 | CO/H2S/CO2 등 가스별 평소 농도 패턴 명확. 임계치 직전 (예: CO 평균 20ppm 인데 35ppm 도달 — 임계 50ppm 미만) 조기 경고 운영 가치 ↑ |
| **전력** | ✅ 적용 | 채널별 평소 부하 패턴 (정격 30~50%) 대비 튐 — 임계치 (정격 100%) 직전 인지 |

→ **두 도메인 모두 적용**. Sliding Window 기반 단순 통계라 도입 비용 낮음.

#### 2.6.4 구현

```python
def _zscore_check(window: deque, value: float, threshold: float = 3.0) -> tuple[bool, float]:
    """슬라이딩 윈도우의 평균·표준편차 기반 Z-score 이상 판정."""
    if len(window) < _INFERENCE_WINDOW:
        return False, 0.0
    arr = np.array(window, dtype=float)
    z = abs(value - arr.mean()) / (arr.std() + 1e-9)  # std=0 분모 폭발 방지
    return bool(z >= threshold), float(z)
```

위치: [fastapi-server/power/services/zscore_anomaly.py](../../fastapi-server/power/services/zscore_anomaly.py) (2026-05-21 분리).

**임계 3σ 결정**: STEP 1 권고 (정규분포 99.7%). 시연 후 false positive 빈도 측정 후 튜닝 (3.5/4.0 후보).

### 2.7 STEP E — Change Point 도입 결정 (2026-05-19)

#### 2.7.1 도입 가치

| 항목 | 운영 가치 | 학습 시연 가치 |
|---|---|---|
| **Change Point (TREND_SHIFT)** | 상태 변화 시점 명시 → 운영자가 "이때부터 패턴 변했다" 인지 + 재학습 시점 결정 자료 | STEP 5 권고 3순위 위험 + concept drift 감지 |

#### 2.7.2 도메인별 적용

| 도메인 | 적용 여부 | 이유 |
|---|---|---|
| 가스 | ❌ **부적합** | 가스 위험은 **단발 spike 위주 (누출 → 즉시 ppm 상승)**. 점진 trend break 가능성 거의 없음. IF + 임계치로 커버 |
| **전력** | ✅ 적용 | **degradation 패턴 (점진 부하 ↑)** 의 시점 명시 가치. ARIMA forecast 가 일부 잡지만 "trend break 시점 명시" 마커 가치 ↑ |

→ **전력만 적용**.

#### 2.7.3 알고리즘 선택 — `ruptures` 회피, 자체 two-window

| 옵션 | 장점 | 단점 | 선택 |
|---|---|---|---|
| `ruptures` 라이브러리 | 다양한 알고리즘 (BinSeg / Pelt / CUSUM) | 추가 의존성, 운영 부담 ↑ | ❌ |
| **자체 two-window 비교** | 의존성 0, 알고리즘 단순 | CUSUM 처럼 누적 drift 미지원 | ✅ |

#### 2.7.4 구현

위치: [fastapi-server/power/services/change_point_service.py](../../fastapi-server/power/services/change_point_service.py)

- 별도 `_cp_windows` (maxlen=60). 본 추론 윈도우 (`_power_windows` maxlen=30) 와 분리
- prev 30 vs curr 30 의 mean / std 비교 — `mean_shift` 와 `std_ratio` 산출
- STABLE→SHIFT 전이 시점만 True 1회 (그 후 SHIFT 동안은 False) — **격상 중복 방지**

**임계 `shift_score >= 2.0` 결정**: 운영 데이터로 튜닝 예정.

### 2.8 5축 결합 우선순위 엔진 (combine_risk_5axis)

위치: [fastapi-server/ai/risk_combine.py](../../fastapi-server/ai/risk_combine.py)

```python
def combine_risk_5axis(threshold, if_pred, arima, z, cp) -> tuple[str, str]:
    base = combine_risk_3axis(threshold, if_pred, arima)  # ← 3축 위임 (회귀 가드)
    if base != "normal":
        return base, ""              # 이미 발화 등급 → Z/CP 격상 안 함
    if change_point:
        return "predict_warn", "change_point"
    if z_score_anomaly:
        return "predict_warn", "zscore"
    return "normal", ""
```

**핵심 의사결정 — base=3축 위임 + Z/CP 격상 분리**:

| 의도 | 의미 |
|---|---|
| W3 회귀 가드 | 기존 3축 매트릭스 (12 cell) 결과 그대로 유지 → AI 가 이미 발화 중인데 Z/CP 가 또 격상시키면 중복 신호 |
| false negative 줄이는 안전망 | 정상으로 판정된 구간에 한해 Z/CP 가 보조 검출기로 동작 |
| escalation_source 추적 | 격상에 기여한 축 명시 — algorithm_source 결정 시 driver 라벨 정확도 ↑ |

### 2.9 combine_risk_3axis 매트릭스 (base, 12 cell)

| threshold \ (IF, ARIMA) | (normal, F) | (normal, T) | (anomaly, F) | (anomaly, T) |
|---|---|---|---|---|
| **normal** | normal | predict_warn | predict_warn | warning |
| **warning** | caution | warning | warning | **danger** |
| **danger** | danger | danger | danger | danger |

→ 두 AI 모델 (IF + ARIMA) 이 동의하는 anomaly 는 한 단계 격상.

---

## 3. 시각 컨텍스트 — night_abnormal

### 3.1 SARIMA 회피 결정

#### 3.1.1 옵션 비교

| 옵션 | 장점 | 단점 | 선택 |
|---|---|---|---|
| **SARIMA(p,d,q,P,D,Q,m)** | 일·주 단위 자동 학습 + 통계 정합성 | 학습 명령 추가 + 1~2주 데이터 누적 선행 + 모델 N 증가 | ❌ 4차 본격 단계로 분리 |
| **STL 분해 + ARIMA** | 잔차 정제 → 더 깨끗한 IF 입력 | 추가 lib 의존성 + 분해 cost | ❌ 4차 본격 단계로 분리 |
| **시각 휴리스틱 (KST 22-05 + 정격 30%)** | 학습 cost 0, 운영자 이해 쉬움 | 정확도 trade-off, 채널별 baseline 부재 | ✅ 시연용 채택 |

#### 3.1.2 선택 근거

- **시연 가치 vs 학습 cost trade-off**: 학습 자료의 5축 정책 엔진 권고 (시각 컨텍스트 명시) 는 휴리스틱으로도 시연 가능.
- **운영 데이터 누적 후 baseline 학습이 자연스러움**: D+30 운영 후 채널별 야간 정상 부하 분포 측정 → baseline 대비 격상으로 전환.

### 3.2 정격 30% 휴리스틱 + KST 게이트

```python
if data_type == "watt" and _is_night_kst_iso(measured_at):
    if value > rated_w * 0.30:  # _NIGHT_THRESHOLD_RATIO
        escalated = _NIGHT_ESCALATION.get(combined, combined)
        # normal → caution, caution → warning, predict_warn → warning
```

위치: [fastapi-server/power/services/night_escalation.py](../../fastapi-server/power/services/night_escalation.py) (2026-05-21 분리).

#### 3.2.1 임계 결정 — 정격 30%

| 임계 후보 | 의미 | 선택 |
|---|---|---|
| 정격 15% | 야간 평균 baseline 추정 | ❌ false positive 다수 (상시 가동 장비) |
| **정격 30%** | 야간 baseline 의 2배 = "야간인데 평소 야간 대비 2배 가동" | ✅ 휴리스틱 채택 |
| 정격 50% | 보수적 — 거의 안 발화 | ❌ 시연 가치 ↓ |

**도메인 직관**: 야간엔 평소 부하 자체가 낮아야 정상. 30% 초과는 "야간 비정상 가동" 의심.

#### 3.2.2 KST 게이트 — UTC 변환 안전 fallback

```python
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)  # naive → UTC 간주
kst_hour = (utc_hour + 9) % 24
# 야간 = 22 <= kst_hour OR kst_hour < 5
```

파싱 실패 시 False 반환 — 야간 격상 미적용 (안전 fallback).

### 3.3 향후 baseline 학습 전환

D+30 ~ D+90: 채널별 야간 baseline 학습 → 정격 % 일률 대신 baseline 대비 격상. 4차 본격 단계에서 SARIMAX 검토.

---

## 4. 알람 결정 + 운영 안전망

### 4.1 AI state 5종

[services/ai_mute.py `AIInferenceState`](../../fastapi-server/services/ai_mute.py) 의 5개 enum:

| state | 의미 | 정적 cover? |
|---|---|---|
| **DISABLED** | AI 비활성 채널 (16채널 중 12채널) | ✅ static_* |
| **WARMING_UP** | AI 활성이지만 윈도우 (30개) 미충족 | ✅ static_* |
| **INFERRED_NORMAL** | AI 추론 결과 정상 | ✅ static_* (cover miss) |
| **INFERRED_FAILED** | AI 추론 예외 발생 | ✅ static_* |
| **FIRED** | AI 추론 결과 발화 등급 | source=ai (정적 cover 보류) |

> **핵심 의사결정**: AI 가 침묵 (DISABLED/WARMING_UP/INFERRED_NORMAL/INFERRED_FAILED) 해도 **정적 임계가 알람을 책임지는 구조**. AI 가 "있으면 좋은 것" 이지 "없으면 안 되는 것" 이 아니어야 하는 산업 IoT 원칙 — [§9.6 외부 리뷰 응답](#9-외부-리뷰-6항목-응답-요약).

### 4.2 quality_guard — comm_failure / overflow / stuck

위치: [fastapi-server/power/services/quality_guard.py](../../fastapi-server/power/services/quality_guard.py)

| 분류 | 트리거 | 처리 |
|---|---|---|
| `comm_failure` | `value is None` | AI 평가 skip + 카운터 `POWER_AI_QUALITY_SKIP_TOTAL.labels("comm_failure")` |
| `sensor_fault_overflow` | `value` 가 유효범위 밖 (예: 음수) | skip |
| `sensor_fault_stuck` | 윈도우 30개가 모두 동일 값 | skip (state 마킹 없이 직전 state 유지) |

**전력 전용** — 가스에는 `value is None` 가드 부재 회귀 위험 ([ai-model-study §4.1](ai-model-study-2026-05-17.md)).

### 4.3 decide_alarm 6 매트릭스

위치: [fastapi-server/power/services/decide_alarm.py](../../fastapi-server/power/services/decide_alarm.py)

```
            AI state\static_risk    normal    warning    danger
            ─────────────────────────────────────────────────────
            DISABLED              → None    → static_*   static_*
            WARMING_UP            → None    → static_*   static_*
            INFERRED_NORMAL       → None    → static_*   static_*  (static cover miss)
            INFERRED_FAILED       → None    → static_*   static_*
            FIRED                 → ai      → ai         ai        (AI 발화 우선)
```

**의도**:
- 행 (AI state) 5개 + 열 (static_risk) 3개 = 매트릭스 15 cell, 그 중 발화 6 cell.
- AI 가 발화 (FIRED) 면 정적 결과와 무관하게 AI source.
- AI 가 발화 안 함 + 정적이 발화 → static_* (cover miss, AI 가 놓친 신호를 정적이 잡음).
- 둘 다 정상 → None (알람 없음).

### 4.4 rate limit + AI mute 동기

#### 4.4.1 60초 rate limit

```python
if combined in _FIRE_LEVELS:
    if now_ts - _last_fired_at.get(sensor_identifier, 0) < 60:
        POWER_AI_RATE_LIMITED_TOTAL.inc()
        asyncio.create_task(forward_inference_e2e(ml_payload, None))  # ML 만 forward
        continue                                                       # push 차단
```

#### 4.4.2 30s vs 60s 검토

| 후보 | 장점 | 단점 | 선택 |
|---|---|---|---|
| 30s | 시연 가시성 ↑ (재발화 빠름) | 운영자 폭주 | ❌ |
| **60s** | 폭주 회피 + 학습 자료의 "운영자 UX" 원칙 | 시연 시 재발화 못 봄 | ✅ |
| 120s | 폭주 완전 차단 | 시연 가시성 손실 큼 | ❌ |

→ **"폭주 회피 > 시연 가시성"** 결정.

#### 4.4.3 AI mute 동기

```python
asyncio.create_task(mark_ai_recent(device_id, channel, rule_level))  # DRF AI mute (ai_fired:* 키)
```

[services/ai_mute.py `mark_ai_recent`](../../fastapi-server/services/ai_mute.py) — DRF Redis 의 `ai_fired:*` 키에 TTL 60s 마킹. rule-based 알람이 AI 발화 중 중복 발화하는 걸 [alarm_dedupe.is_ai_mute_active](../../drf-server/apps/alerts/services/alarm_dedupe.py) 가 차단.

→ **AI 와 rule 알람 중복 방지** — 같은 센서의 두 알람이 동시에 운영자에게 보이는 걸 차단.

### 4.5 algorithm_source priority (6단계)

```python
if night_escalated:                                   algorithm_source = "night_abnormal"
elif prediction == "anomaly" and arima_violation:     algorithm_source = "combined"
elif escalation_source == "change_point":             algorithm_source = "change_point"
elif arima_violation:                                 algorithm_source = "arima"
elif escalation_source == "zscore":                   algorithm_source = "zscore"
elif prediction == "anomaly":                         algorithm_source = "isolation_forest"
else:                                                 algorithm_source = ""
```

**priority 의도**:
1. **night > combined > change_point > arima > zscore > IF** — 강한 신호 위주.
2. **z/cp 는 escalation_source 일치 시만 라벨 채택** — base 가 이미 발화 등급인데 z/cp 발생한 케이스에서 라벨이 driver 와 어긋나는 문제 방지 ([2026-05-19 코드리뷰 §2.1 보강](../../docs/codereviews/2026_05_19/power-5axis-policy-flow.md)).

**운영자 친화 워딩** (`_ALGORITHM_SOURCE_PHRASE` dict):
- `isolation_forest` → "이상 수치 탐지"
- `arima` → "이상 패턴 탐지"
- `combined` → "이상 수치·패턴 동시 탐지"
- `zscore` → "통계 이상 수치"
- `change_point` → "패턴 변화 탐지"
- `night_abnormal` → "야간 이상 가동"

→ DRF [constants.ALGORITHM_SOURCE_PHRASE](../../drf-server/apps/core/constants.py) 와 **단일 동기**.

---

## 5. 채널 확장 전략 — 1ch → 4ch → 16ch

### 5.1 단계별 모델 수 스케일 (un-downgrade 기준)

| 단계 | 시점 | 범위 | IF | ARIMA | 합계 | 위치 |
|---|---|---|---|---|---|---|
| **1** | ~2026-05-20 | 1채널 PoC (ch1 watt) | 1 (univariate) | 1 | 2 | _INFERENCE_ENABLED_CHANNELS = {(1,"watt")} |
| **2 (현재)** | 2026-05-21 | 4채널 (ch1/9/14/15 watt) | 4 (채널별) | 4 (채널별) | 8 | _INFERENCE_ENABLED_CHANNELS = {(1,"watt"), (9,"watt"), (14,"watt"), (15,"watt")} |
| 3 | D+30 ~ D+90 | 1 device 16채널 | 1 (panel-multivariate) | 16 (channel별) | 17 | 전 16채널 활성화 + auto-arima |
| 4 | D+90 ~ | N devices | N | 16N | **17N** | 클러스터링 PoC |

### 5.2 4채널 부하 종류 다양성 기준 (2026-05-21)

| 채널 | 부하 종류 | 정격 | 의도 |
|---|---|---|---|
| ch1 | 압연기 모터 | 7.5kW | 점진 부하 ↑ (베어링 마모) 시나리오 |
| ch9 | 메인 전력반 3상 | 15kW | 3상 동시 가동·정전 시나리오 |
| ch14 | 공조설비 모터 | 5.5kW | 시간대별 가동 패턴 (시각 분기 가치) |
| ch15 | 조명/제어 단상 | 1kW 220V | 저부하 채널 정확도 검증 |

**왜 ch2~8 모터 동질군 제외**: 학습 데이터 중복 최소 (압연기 7.5kW 모터가 7대 동일군). 부하 종류 다양성 검증이 목적이라 동질군은 1개만 활성.

**참조**: [docs/codereviews/2026_05_21/power-ai-multichannel-application-review.md](../../docs/codereviews/2026_05_21/power-ai-multichannel-application-review.md).

### 5.3 16ch 확장 시 인프라 부담

| 영역 | 1ch | 4ch | 16ch (전체) | 1 device 의 부담 |
|---|---|---|---|---|
| ARIMA 모델 수 | 1 | 4 | 16 | × 16 (학습 cost) |
| 메모리 (모델 로드) | 1 entry | 4 | 16 | × 16 (LRU cap 부재) |
| 학습 batch 시간 | 30초 | 2분 | 8분 (순차) | 병렬 학습 필요 |
| auto-arima 튜닝 | 1회 | 4회 | 16회 | (p,d,q) 자동화 필요 |

→ **16ch 진입 전 인프라 필수**:
1. **Lazy + LRU 캐시** — `_cache` 에 cap 추가 (현재 TTL eviction 만)
2. **auto-arima** — `pmdarima.auto_arima` 또는 자체 AIC/BIC 그리드
3. **클러스터링 PoC** — DTW 거리로 부하 동질군 묶기 → 클러스터당 모델 1개

### 5.4 D+30 운영 데이터 누적 후 결정

4채널 × 4주 운영 데이터 분석 → 다음 정량 측정:
- 채널별 IF anomaly rate / ARIMA violation rate / Z-score anomaly rate / CP detection rate
- algorithm_source 분포 (라벨별 발화 비율)
- false positive 빈도 (운영자 ack 율)

→ 결과로 (a) 16ch 확장 의사결정 / (b) Z·CP 임계 튜닝 / (c) 가중치 조정 / (d) auto-arima 도입 우선순위 결정.

---

## 6. watt 단독 추론 — A/V 미추론

### 6.1 의사결정 매트릭스

| 옵션 | 장점 | 단점 | 선택 |
|---|---|---|---|
| **watt 만** | P = V × I 종합 신호. 학습·운영 모델 수 1/3 | A/V 의 도메인 특성 (방향성·위상) 미활용 | ✅ 시연용 |
| watt + A (다변량 IF) | 전류 파형 이상 (절연 열화·역률) 조기 검출 | 모델 N × 2, 학습 cost ↑ | ❌ D+30 PoC |
| watt + A + V (3D 다변량) | 가스 다변량 IF 패턴 재활용 | 채널 간 독립성 위반 (전압은 라인 공통) | ❌ 4차 본격 |

### 6.2 선택 근거

- **시연 가치 우선**: 시연 핵심 메시지는 "AI 가 부하 이상을 잡는다" — watt 만으로 충분히 시연 가능.
- **PoC 단계의 모델 N 최소화**: A/V 까지 학습하면 3×N 채널 학습·운영 부담. 1ch PoC 의 검증 목적과 비례하지 않음.
- **A/V 도메인 가치는 4차 본격 도입 시점에 맞음**: [4차_향후확장방향_문서 §4](../4차_향후확장방향_문서.md) — 실 게이트웨이 도입 + 라벨링 데이터 누적 후가 적절.

### 6.3 후속 plan

- D+30: 운영 데이터 누적 → A 도 watt 와 함께 다변량 IF feature 로 묶는 PoC.
- 4차 단계: SARIMAX + W/A/V 다변량 정식 도입.

---

## 7. 학습 파이프라인

### 7.1 train_anomaly_model (전력 IF)

위치: [drf-server/apps/ml/management/commands/train_anomaly_model.py](../../drf-server/apps/ml/management/commands/train_anomaly_model.py)

```bash
docker compose exec drf python manage.py train_anomaly_model \
    --sensor-type power \
    --since 2026-05-01 --until 2026-05-20 \
    --activate
```

산출물:
- `/app/ml_models/power_if_v{N}.pkl` (호스트의 `drf-server/ml_models/`)
- MLModel row (`algorithm="isolation_forest"`, `sensor_identifier=""`, `is_active=True`)

**4피처 (전력 단변량)**: value / roll_mean / roll_std / diff.
**학습 데이터 표본 수**: max_rows=10000 (ConvergenceWarning 회피).

### 7.2 train_arima_power_model (전력 ARIMA)

위치: [drf-server/apps/ml/management/commands/train_arima_power_model.py](../../drf-server/apps/ml/management/commands/train_arima_power_model.py)

```bash
docker compose exec drf python manage.py train_arima_power_model \
    --device-id 1 --channel 1 --data-type watt \
    --since 2026-05-01 --until 2026-05-20 \
    --activate
```

산출물:
- `/app/ml_models/power_arima_v{N}_power_device_{mac}_chN_watt.pkl`
- MLModel row (`algorithm="arima"`, `sensor_identifier="power:device_{mac}:chN:watt"`)

**(p,d,q) 기본값 = (1,1,1)** — 하드코딩. auto-arima 미적용 (D+30 sprint 후속).

### 7.3 MLModel 4축 매칭

| 차원 | 의미 |
|---|---|
| `sensor_type` | "gas" or "power" |
| `algorithm` | "isolation_forest" or "arima" |
| `sensor_identifier` | "" (sensor_type 단위) or "power:device_{mac}:chN:watt" (채널 단위) |
| `version` | 학습 버전 (재학습 시 증가) |

→ 4축 unique constraint. [migration 0002](../../drf-server/apps/ml/migrations/) 에서 도입 (W1.1).

### 7.4 fastapi 모델 로드 (TTL 캐시 + reload endpoint)

위치: [fastapi-server/ai/router.py](../../fastapi-server/ai/router.py)

```python
async def _get_or_load(sensor_type, sensor_identifier=""):
    # 1. cache hit (TTL 미만) → return entry
    # 2. cache miss → DRF /api/ml/models/active/ 조회 → .pkl joblib 로드 → 캐시 저장
```

- **캐시 단위**: `(sensor_type, algorithm, sensor_identifier)` 튜플 키
- **TTL**: `ML_MODEL_CACHE_TTL_SEC` (기본 300초)
- **수동 evict**: `POST /ai/reload?sensor_type=power&algorithm=arima&sensor_identifier=...`

**LRU cap 부재** — 다채널 확장 시 메모리 폭증 위험 ([§10.4](#104-lru-cap-미적용)).

### 7.5 가스 vs 전력 매칭 단위 차이

| 영역 | 가스 | 전력 |
|---|---|---|
| ARIMA pkl 매칭 | 가스명별 분리 (`arima_co.pkl`) | sensor_identifier 분리 |
| MLModel row (ARIMA) | **없음** — `gas_service.py` 모듈 import 시 joblib 직접 로드 | 있음 — 운영 추적 가능 |
| sensor_id 가정 | sensor_id=1 하드코딩 | mac 동적 |

**가스 측 추적 한계**: ARIMA 모델 학습 버전·기간 DB 흔적 없음. 시연 후 가스 담당자 task 로 통합 예정.

---

## 8. 데이터 흐름 (E2E)

### 8.1 진입점 — fastapi 4 router

[fastapi-server/power/routers/power_router.py](../../fastapi-server/power/routers/power_router.py)

```
recv_onoff   → update_power_state("onoff", ...)   + DRF POST (event)
recv_current → update_power_state("current", ...) + DRF POST (data)
recv_voltage → update_power_state("voltage", ...) + DRF POST (data)
recv_watt    → update_power_state("watt", ...)    + ★ process_anomaly_inference ★ + DRF POST (data)
```

**watt 만 AI 추론 호출**. 다른 3종은 raw 저장 + 상태 갱신만.

### 8.2 AI 추론 — process_anomaly_inference 5단계

[anomaly_inference.py](../../fastapi-server/power/services/anomaly_inference.py) (2026-05-21 분리)

```
[16채널 루프]
   ├ 1. quality_guard skip (comm_failure / overflow / stuck) — AI 평가 skip
   │
   ├ 2. 정적 임계 평가 (모든 채널 공통)
   │     static_risk = evaluate_static_risk_from_cache(...)
   │
   ├ 3. AI 비활성 채널 → DISABLED + 정적 cover (12채널)
   │
   ├ 4. AI 활성 채널 (4채널)
   │     ├ 윈도우 누적 (deque maxlen=30)
   │     ├ 미충족 → WARMING_UP + 정적 cover
   │     ├ stuck → skip
   │     ├ 5축 추론
   │     │     ├ IF: 4피처 → score + prediction
   │     │     ├ ARIMA: forecast + 95% CI 위반
   │     │     ├ Z-score: |z| >= 3σ
   │     │     ├ CP: two-window 비교
   │     │     └ threshold: 정격 %
   │     │
   │     ├ combine_risk_5axis → combined + escalation_source
   │     │
   │     ├ 야간 격상 (watt + KST 22-05 + 정격 30%)
   │     │
   │     ├ algorithm_source priority 결정 (6단계)
   │     │
   │     ├ rate limit (60s) + AI state 마킹 (FIRED/INFERRED_NORMAL/INFERRED_FAILED)
   │     │
   │     └ decide_alarm 6 매트릭스 → source 결정 (ai vs static_*)
   │
   └ 5. push + forward (단일)
         ├ WS: push_alarm → Redis BRPOP → broadcast_loop → 브라우저
         └ DRF: forward_inference_e2e
                 ├ /api/ml/anomaly-results/ (MLAnomalyResult, 5축 features 영속화)
                 └ /api/monitoring/power/event/ (AlarmRecord + Event 생성, AI source 만)
```

### 8.3 DRF forward 3종

| 경로 | 호출 시점 | 영속화 모델 |
|---|---|---|
| `/api/monitoring/power/data/` | router 의 `bg.add_task` (fire-and-forget) | `PowerData` (16채널 raw + channels[] JSON) |
| `/api/ml/anomaly-results/` | `process_anomaly_inference` 항상 (rate limit 통과 여부 무관) | `MLAnomalyResult` (score + features + risk_classified 5단계) |
| `/api/monitoring/power/event/` | `process_anomaly_inference` 의 source=ai 만 | `AlarmRecord` + `Event` (algorithm_source 라벨링) |

**핵심 의사결정**: ML forward 는 매번 / Alarm forward 는 source=ai 만 / Power raw 는 watt/current/voltage/onoff 모두 매번 — **운영 추적 (ML) 과 알람 영속화 (Alarm) 와 raw 보존 (Power) 의 책임 분리**.

### 8.4 WebSocket broadcast — Redis BRPOP

[fastapi-server/websocket/services/broadcast.py](../../fastapi-server/websocket/services/broadcast.py)

```
process_anomaly_inference → push_alarm → Redis LPUSH diconai:ws:alarms
                                             ↓
                                         broadcast_loop (1초 주기 BRPOP)
                                             ↓
                                         sensor_clients (모든 WS 클라이언트)
                                             ↓
                                         브라우저 알람 토스트
```

### 8.5 16채널 equipment[] 별도 흐름

[equipment_builder.py:build_equipment](../../fastapi-server/power/services/equipment_builder.py) (2026-05-21 분리)

- AI 결과와 **무관**한 대시보드 색상 표시
- 1초 주기로 `power_latest` 읽어 16채널 × {watt/voltage/current/onoff + 3축 risk} 조립
- 정격 % 기반 risk 산출 — DRF threshold_service 와 동일 시맨틱
- broadcast_loop 가 sensor_clients 에 broadcast

**왜 분리**: 알람 (process_anomaly_inference) 과 대시보드 표시 (build_equipment) 는 책임이 다름. 대시보드는 매 1초 갱신, 알람은 위험 변화 시에만.

---

## 9. 외부 리뷰 6항목 응답 요약

외부 리뷰가 "1차 MVP" 로 평가한 6개 항목이 모두 의도된 결정임을 § 별로 매핑.

| 외부 비판 | 본 문서 § | 핵심 응답 |
|---|---|---|
| **① watt 단독 추론** (A/V 미추론) | [§6](#6-watt-단독-추론--av-미추론) | 1ch PoC 의 의도된 스코핑. P = V × I 종합 신호 + 모델 N 최소화. A/V 는 4차 본격 단계로 분리 |
| **② 16채널 중 4채널만 활성** | [§5](#5-채널-확장-전략--1ch--4ch--16ch) | 부하 종류 다양성 검증의 첫 단계 (모터/전력반/공조/조명). D+30 운영 데이터 누적 후 16ch 확장 의사결정 |
| **③ 윈도우 30 적정성** | [§2.4.1](#241-4피처-선택-근거) + [§12](#12-후속-로드맵) | 1Hz × 30초 — 추론 latency 우선. 시연 후 false positive 빈도 측정 → window 60~120 실험 |
| **④ night_abnormal 정격 30%** | [§3](#3-시각-컨텍스트--night_abnormal) | SARIMA 회피 + 시각 휴리스틱 — 학습 cost 0 + 운영자 이해 쉬움. D+30 채널별 baseline 학습 전환 |
| **⑤ ARIMA 1-step + 95% CI 단발 spike 한계** | [§2.5.2](#252-arima111-의도된-한계) | "의도된 한계 vs 버그" 명시적 구분 + 4축 보완 (IF + threshold). D+30 multi-step PoC |
| **⑥ ARIMA base 가중치 (IF 동급)** | [§1.5](#15-결론-매트릭스) | 도메인 의존 결정 — 전력 = un-downgrade 필수, 가스 = 격하 충분. D+30 confusion matrix 정당성 검증 |

**참조**: [skill/study/power-ai-design-decisions-2026-05-21.md](power-ai-design-decisions-2026-05-21.md) (오늘 작성 — 외부 리뷰 6항목 단답).

---

## 10. 한계·트러블슈팅

> 본 § 의 모든 한계는 "버그" 가 아닌 **"의도된 1차 MVP 스코핑"** + **"보완 축으로 커버"** 로 분류.

### 10.1 ARIMA(1,1,1) 단발 spike 한계 (의도된 동작)

#### 증상

8000W (정격 7500W 의 107%) 강제 주입 시:
- threshold = `danger` ✓
- IF prediction = `anomaly` ✓
- **ARIMA violation = `False`** ✗ — 단발 spike 인데 forecast 신뢰구간 안 들어옴

#### 원인

ARIMA(1,1,1) 의 **빠른 적응 특성** — `apply(endog=values)` 호출 시점에 마지막 1~3틱 spike 가 입력에 포함되어 모델이 즉시 자기회귀 학습 패턴으로 적응 → `get_forecast(steps=1)` 의 신뢰구간이 spike 근처로 따라감 → actual 이 CI 안에 들어옴.

#### 해결

다른 축이 잡으므로 시스템 전체는 정상. **ARIMA 가 잡지 못해도 다른 축이 잡으므로 의도된 동작**.

#### 향후 정확도 향상 옵션 (필수 아님)

1. **forecast steps 확장** (steps=1 → steps=5~10) — multi-step 으로 미래 N틱 예측 + 누적 위험 (PREDICTIVE_ALERT)
2. **order 자동 선택** (`pmdarima.auto_arima`) — (1,1,1) 고정 → AIC/BIC 최소화
3. **SARIMAX 도입** — seasonal order 추가 → 시각 사이클 자동 학습
4. **재학습 cadence 자동화** — 주 단위 retrain task

**참조**: [skill/troubleshooting/0519_arima-single-spike-limit.md](../troubleshooting/0519_arima-single-spike-limit.md).

### 10.2 SARIMA 미적용 — 휴리스틱 우회 ([§3.1](#31-sarima-회피-결정))

### 10.3 IF feature 빈약 — hour/day/자기상관 미적용

[IF_ARIMA_팀공유 방향 #2](IF_ARIMA_팀공유.md) 권고 중 미적용:
- `hour_of_day` / `day_of_week` (contextual anomaly 추가 검출)
- 잔차 자기상관 (collective anomaly)

→ **5축 엔진의 외부 축 (Z + CP) 으로 일부 보강** — IF 안에 피처 추가 대신 외부 축으로.

### 10.4 LRU cap 미적용

현재 `_cache: dict[tuple, _CachedModel]` + TTL eviction 만 운영. **LRU cap 없음 → 디바이스 N 증가 시 메모리 폭증 위험**.

→ D+30 sprint 의 확장성 사전 대응 과제.

### 10.5 auto-arima 미사용

전력 ARIMA 학습 시 `--p 1 --d 1 --q 1` 하드코딩 (기본값). 다채널 확장 시 (p,d,q) 튜닝 부담 ↑.

→ D+30 ~ D+90 sprint 의 정확도 본격 개선 과제.

### 10.6 Online ARIMA 미적용

batch refit 운영 (W5 후속). Kalman filter / `RecursiveLS` 점진 update 미도입.

→ D+90+ 장기 과제 (R&D).

### 10.7 가스 `value is None` 가드 회귀

[ai-model-study §4.1](ai-model-study-2026-05-17.md) — 가스 `gas_service.process_gas_data` 는 `value is None` 가드 없음. 통신 불능 시 None 이 deque 에 들어가 sklearn 입력 에러 가능.

→ 전력 패턴 (`if value is None: continue`) 을 가스에도 백포팅 필요 — **가스 담당자 task**.

---

## 11. 의사결정 패턴 4가지

> 본 작업 (2026-05-08 ~ 2026-05-21) 동안 반복적으로 적용된 의사결정 framework. 신규 AI 모델 도입 시 재활용 가능.

### 11.1 1차 PoC → 시연 후 본격 확장

**의미**: MVP 단계는 의도적 스코핑. 시연 후 운영 데이터 누적 후 본격 확장.

**적용 사례**:
- 채널 범위 (1ch → 4ch → 16ch)
- 윈도우 30
- 시각 휴리스틱 (SARIMA 회피)
- IF feature (4피처 → hour/ACF 보강)
- watt 단독 (→ A/V 다변량)

### 11.2 모델 한계 명시 + 다른 축으로 보완

**의미**: 어떤 모델도 모든 패턴을 잡지 못함. 한계는 인정하고 다른 축이 커버.

**적용 사례**:
- ARIMA(1,1,1) 단발 spike 한계 → IF + threshold 가 잡음
- SARIMA 회피 → 시각 휴리스틱 (정격 30%) 으로 우회
- IF feature 빈약 → Z-score + CP 가 외부 축으로 보강
- AI 침묵 → 정적 임계가 cover (decide_alarm 매트릭스)

### 11.3 도메인 의존 architecture

**의미**: 가스와 전력은 도메인 특성이 다름 → architecture 비대칭은 의도된 설계.

**적용 사례**:
- ARIMA 격하 (가스) vs un-downgrade (전력)
- night_abnormal (전력만)
- Change Point (전력만 — degradation 도메인)
- 다채널 (전력만 — 채널 독립성)
- 다변량 IF (가스 — 공기 화학)

### 11.4 운영 데이터 누적 후 정당성 검증

**의미**: 통계적 정당성·임계 튜닝은 운영 데이터 없이는 진위 불명. PoC 단계는 합리적 default 채택 후 D+30 측정 → 조정.

**적용 사례**:
- ARIMA 가중치 (IF 동급) → D+30 confusion matrix 측정
- 정격 30% cutoff → D+30 채널별 야간 baseline 측정
- 윈도우 30 → D+30 false positive 빈도 측정
- Z-score 3σ / CP shift_score 2.0 → 운영 데이터로 튜닝

---

## 12. 후속 로드맵

### 12.1 D-day (2026-06-14) 까지 — 안정화 (D-24 ~ D+0)

**원칙**: 추가 모델 변경 X — 5축 엔진 + 시각 휴리스틱 + 4채널 PoC 로 시연 충분.

| 항목 | 시점 | 비고 |
|---|---|---|
| `feature/0519_power_add_chanel` 4채널 안정화 | D-26 ~ D-14 | 본 sprint 산출 |
| `feature/0519_power_add_chanel` 의 `power_service.py` 분리 + §6 주석 정비 | 2026-05-21 (D-24) | 본 작업 |
| 시연 리허설 — Z-score / CP false positive 빈도 측정 | D-7 ~ D-3 | dummy 1주 가동 후 발화 카운트. threshold 튜닝 (Z=3.0 → 3.5/4.0?) |
| W4.b metrics 라벨 추가 (`ALARM_FIRED_TOTAL.algorithm_source`) | D-14 ~ D-7 | 발화 분포 가시화 |

### 12.2 D+1 ~ D+30 sprint — 정확도 본격 개선

| 순서 | 액션 | 효과 | 의존성 |
|---|---|---|---|
| 1 | FFT·ACF 분석 (가스/전력) | 일·주 단위 주기성 정량 확인 → SARIMA 도입 근거 | 운영 데이터 1~2주 누적 |
| 2 | STL 분해 PoC | residual 분포 깨끗함 검증. IF false positive 측정 | 1번 결과 |
| 3 | IF feature 확장 — `hour_of_day` / `day_of_week` / 잔차 자기상관 | 방향 #2 완성. contextual / collective anomaly 추가 검출 | feature_service 확장 |
| 4 | 도메인 임계 공식 문서화 | 가스 안전기준 (CO 50ppm 등) · 전력 부하 정책 · Z-score 운영 threshold | 운영자 면담 |
| 5 | ARIMA confusion matrix 측정 | un-downgrade 가중치 정당성 검증 | 운영 데이터 |

### 12.3 D+30 ~ D+90 sprint — 확장성 본격 + 16채널

| 순서 | 액션 | 효과 |
|---|---|---|
| 6 | Lazy + LRU 캐시 도입 | 방향 #7 완성. `_cache` 에 LRU cap (운영 메모리 안정) |
| 7 | `_INFERENCE_ENABLED_CHANNELS` 16채널 확장 | 다채널 운영 시 모델 N 부담 측정 |
| 8 | SARIMA / STL+ARIMA 교체 | 일·주 주기 검출 시 SARIMA(p,d,q,P,D,Q,m) 학습 명령 추가 |
| 9 | CUSUM 결합 | Change Point (STEP E) + CUSUM 누적합 → drift 누적 강화 |
| 10 | 디바이스 클러스터링 PoC | DTW 거리 / 시계열 임베딩으로 N 디바이스 군집화 → 클러스터당 모델 1개 |
| 11 | auto-arima | (1,1,1) 고정 → AIC/BIC 자동 선택 |

### 12.4 D+90+ 장기 — 글로벌 모델

| 순서 | 액션 | 효과 |
|---|---|---|
| 12 | Online ARIMA | Kalman filter 기반 점진 update. statsmodels `RecursiveLS` 또는 외부 lib |
| 13 | 클러스터 기반 운영 정착 | 1000+ 디바이스 대응 |
| 14 | Global model 실험 | LightGBM + device_id categorical feature 또는 시계열 파운데이션 모델 (R&D) |

---

## 부록 A. 코드 위치 인덱스

### A.1 fastapi-server (추론·결합·알람)

| 영역 | 파일 |
|---|---|
| 진입 router | [power/routers/power_router.py](../../fastapi-server/power/routers/power_router.py) |
| 진입 façade | [power/services/power_service.py](../../fastapi-server/power/services/power_service.py) |
| AI 추론 핵심 | [power/services/anomaly_inference.py](../../fastapi-server/power/services/anomaly_inference.py) |
| 5축 결합 | [ai/risk_combine.py](../../fastapi-server/ai/risk_combine.py) `combine_risk_5axis` (base=3축 위임) |
| Z-score (STEP D) | [power/services/zscore_anomaly.py](../../fastapi-server/power/services/zscore_anomaly.py) `_zscore_check` |
| Change Point (STEP E) | [power/services/change_point_service.py](../../fastapi-server/power/services/change_point_service.py) `detect_change_point` |
| 야간 격상 | [power/services/night_escalation.py](../../fastapi-server/power/services/night_escalation.py) `_is_night_kst_iso` + `_NIGHT_ESCALATION` |
| 정적 임계 평가 | [power/services/threshold_eval.py](../../fastapi-server/power/services/threshold_eval.py) `calculate_power_risk` / `evaluate_static_risk_from_cache` |
| quality_guard | [power/services/quality_guard.py](../../fastapi-server/power/services/quality_guard.py) |
| decide_alarm 매트릭스 | [power/services/decide_alarm.py](../../fastapi-server/power/services/decide_alarm.py) |
| AI 모델 로드 (IF + ARIMA) | [ai/router.py](../../fastapi-server/ai/router.py) `_get_or_load` / `_get_or_load_arima` / `_arima_forecast` / `_build_feature_row` |
| equipment[] 조립 | [power/services/equipment_builder.py](../../fastapi-server/power/services/equipment_builder.py) `build_equipment` |
| WebSocket broadcast | [websocket/services/broadcast.py](../../fastapi-server/websocket/services/broadcast.py) |
| Redis 알람 큐 | [websocket/services/alarm_queue.py](../../fastapi-server/websocket/services/alarm_queue.py) |
| AI mute 동기 | [services/ai_mute.py](../../fastapi-server/services/ai_mute.py) `mark_ai_recent` / `mark_ai_state` / `AIInferenceState` |
| 추론 결과 forward | [services/anomaly_alarm.py](../../fastapi-server/services/anomaly_alarm.py) `forward_inference_e2e` |
| algorithm_source 워딩 | [power/services/anomaly_inference.py](../../fastapi-server/power/services/anomaly_inference.py) `_ALGORITHM_SOURCE_PHRASE` |

### A.2 drf-server (학습·영속화)

| 영역 | 파일 |
|---|---|
| IF 학습 command | [apps/ml/management/commands/train_anomaly_model.py](../../drf-server/apps/ml/management/commands/train_anomaly_model.py) |
| ARIMA 학습 command (전력) | [apps/ml/management/commands/train_arima_power_model.py](../../drf-server/apps/ml/management/commands/train_arima_power_model.py) |
| MLModel | [apps/ml/models/ml_model.py](../../drf-server/apps/ml/models/ml_model.py) |
| MLAnomalyResult | [apps/ml/models/ml_anomaly_result.py](../../drf-server/apps/ml/models/ml_anomaly_result.py) |
| algorithm_source 워딩 | [apps/core/constants.py](../../drf-server/apps/core/constants.py) `ALGORITHM_SOURCE_PHRASE` |
| 학습 데이터 export | [apps/ml/services/dataset_service.py](../../drf-server/apps/ml/services/dataset_service.py) |
| AnomalyAlarmRecord 수신 view | [apps/alerts/views/anomaly_alarm_record.py](../../drf-server/apps/alerts/views/anomaly_alarm_record.py) |
| 룰 측 mute 가드 | [apps/alerts/services/alarm_dedupe.py](../../drf-server/apps/alerts/services/alarm_dedupe.py) `is_ai_mute_active` |

### A.3 dummy / 시나리오

| 영역 | 파일 |
|---|---|
| 전력 dummy | [fastapi-server/dummies/power_dummy.py](../../fastapi-server/dummies/power_dummy.py) |
| 가스 dummy | [fastapi-server/dummies/gas_dummy.py](../../fastapi-server/dummies/gas_dummy.py) |

---

## 부록 B. 관련 문서 인덱스

### B.1 의사결정·근거 계열

| 문서 | 핵심 내용 |
|---|---|
| [skill/study/ai-model-study-2026-05-17.md](ai-model-study-2026-05-17.md) | un-downgrade vs 격하 도메인 결정 근거 (§2.4 매트릭스) + 전력 단계별 모델 수 스케일 |
| [skill/study/IF_ARIMA_팀공유.md](IF_ARIMA_팀공유.md) | IF + ARIMA 원리 + 정확도·확장성 한계 + 해결 방향 8가지 |
| [skill/study/power-ai-design-decisions-2026-05-21.md](power-ai-design-decisions-2026-05-21.md) | 외부 리뷰 6항목 의사결정 단답 (오늘 작성) |
| [skill/plan/power-ai-un-downgrade-phase2.md](../plan/power-ai-un-downgrade-phase2.md) | un-downgrade 원본 plan |
| [skill/plan/power-ai-un-downgrade-phase2-apply.md](../plan/power-ai-un-downgrade-phase2-apply.md) | un-downgrade 적용 plan (옵션 A — 가스 보호) |
| [skill/plan/anomaly-detection-zscore-changepoint.md](../plan/anomaly-detection-zscore-changepoint.md) | Z-score (STEP D) + CP (STEP E) 도입 결정 (2026-05-19) |
| [skill/plan/power-zscore-changepoint-apply.md](../plan/power-zscore-changepoint-apply.md) | Z-score + CP 전력 적용 plan |
| [skill/plan/power-ai-multichannel-activate.md](../plan/power-ai-multichannel-activate.md) | 4채널 활성화 plan (2026-05-21) |
| [skill/4차_향후확장방향_문서.md](../4차_향후확장방향_문서.md) | 4차 본격 도입 로드맵 (AI 정식 / 임계치 DB / 모바일 앱) |

### B.2 적용 현황 계열

| 문서 | 핵심 내용 |
|---|---|
| [skill/study/IF_ARIMA_적용현황_2026_05_19.md](IF_ARIMA_적용현황_2026_05_19.md) | 8개 권고 영역 × 적용도 매트릭스 (5축 엔진까지의 회고) |
| [docs/codereviews/2026_05_19/power-5axis-policy-flow.md](../../docs/codereviews/2026_05_19/power-5axis-policy-flow.md) | 5축 코드 흐름 (combine_risk_5axis) |
| [docs/codereviews/2026_05_21/power-ai-multichannel-activation.md](../../docs/codereviews/2026_05_21/power-ai-multichannel-activation.md) | 4채널 활성화 Before/After 코드리뷰 |
| [docs/codereviews/2026_05_21/power-ai-multichannel-application-review.md](../../docs/codereviews/2026_05_21/power-ai-multichannel-application-review.md) | 4채널 적용 검증 보고서 (트러블슈팅 포함) |

### B.3 한계·트러블슈팅 계열

| 문서 | 핵심 내용 |
|---|---|
| [skill/troubleshooting/0519_arima-single-spike-limit.md](../troubleshooting/0519_arima-single-spike-limit.md) | ARIMA(1,1,1) 단발 spike 한계 — 8000W 검증 케이스 + 4축 보완 |
| [skill/troubleshooting/0519_statsmodels-image-rebuild-missing.md](../troubleshooting/0519_statsmodels-image-rebuild-missing.md) | statsmodels 이미지 rebuild 누락 트러블슈팅 |

### B.4 학습 자료 (외부 + 사용자 정리)

| 문서 | 핵심 내용 |
|---|---|
| [skill/STEP 5 — 디코나이 AI 기반 위험 예측 개발 로드맵.md](../STEP%205%20—%20디코나이%20AI%20기반%20위험%20예측%20개발%20로드맵.md) | 5단계 정책 엔진 권고 (STEP B ~ STEP G) |
| [AI 관련 미정리 총 내용.md](../../AI%20관련%20미정리%20총%20내용.md) | 사용자 본인 정리본 (가스 vs 전력 4영역 비교, 50KB) |
| [skill/전력 AI un-downgrade (IF + ARIMA) 통합 작업 복습 및 보고.md](../전력%20AI%20un-downgrade%20%28IF%20%2B%20ARIMA%29%20통합%20작업%20복습%20및%20보고.md) | un-downgrade 통합 작업 복습·보고 |
| [skill/AI/1️⃣ AI 이상 탐지.md](../AI/1️⃣%20AI%20이상%20탐지.md) | AI 이상 탐지 학습 자료 |

---

## 부록 C. 학습 자료 추천 (외부)

[IF_ARIMA_팀공유 Part 9](IF_ARIMA_팀공유.md) 에서 가져옴:

| 주제 | 자료 |
|---|---|
| ARIMA | "Forecasting: Principles and Practice" (Rob Hyndman) — 무료 온라인 책 |
| Isolation Forest | 원논문 "Isolation Forest" (Liu et al., 2008) — 12페이지 |
| STL 분해 | statsmodels 공식 문서의 STL 튜토리얼 |
| 변화점 탐지 | `ruptures` 라이브러리 문서 |
| 시계열 클러스터링 | `tslearn` 라이브러리 + DTW 개념 |

---

## 부록 D. 핵심 용어 정리

| 용어 | 한 줄 정의 |
|---|---|
| **격하 (downgrade)** | ARIMA 잔차를 IF 입력 피처로 흡수. ARIMA 가 독립 algorithm 이 아닌 피처 공급원 |
| **un-downgrade** | ARIMA 를 IF 와 동급 algorithm 으로 분리. forecast + 95% 신뢰구간 위반을 독립 판단자로 사용 |
| **5축 (combine_risk_5axis)** | Threshold + IF + ARIMA + Z-score + Change Point 의 우선순위 결합 엔진 |
| **base (3축)** | combine_risk_3axis (Threshold × IF × ARIMA) — W3 회귀 가드 보존 |
| **escalation_source** | Z/CP 가 격상에 기여한 경우 라벨 ("zscore" / "change_point"). base != "normal" 면 빈 문자열 |
| **algorithm_source** | 알람 발화 시 운영자에게 표시되는 driver 라벨 (6단계 priority) |
| **AI state 5종** | DISABLED / WARMING_UP / FIRED / INFERRED_NORMAL / INFERRED_FAILED — DRF AI mute 동기 |
| **decide_alarm** | AI state × static_risk 6 매트릭스 → source 결정 (ai vs static_* vs None) |
| **rate limit (60s)** | 같은 sensor_identifier 의 알람 push 폭주 회피. ML forward 는 매번 |
| **sensor_identifier** | ARIMA 매칭 단위 (`power:device_{mac}:chN:watt`). IF 는 sensor_type 단위 |
| **night_abnormal** | KST 야간 (22-05) + watt > 정격 30% 시 한 단계 격상 — SARIMA 회피 휴리스틱 |
| **quality_guard** | comm_failure / sensor_fault_overflow / sensor_fault_stuck 사전 차단 — 전력 전용 |
| **MLModel 4축** | (sensor_type, algorithm, sensor_identifier, version) unique 매칭 |
| **MLAnomalyResult** | 추론 결과 영속화 (score + features + risk_classified 5단계) |
| **AlarmRecord** | 알람 영속화 (algorithm_source 라벨 포함) — source=ai 만 |
| **AI mute (ai_fired:*)** | DRF Redis TTL 60s 키. rule-based 알람의 AI 중복 발화 방지 |

---

> **본 문서의 핵심 메시지**:
> 전력 AI 의 architecture (un-downgrade + 5축 결합 + night_abnormal + decide_alarm 6 매트릭스) 는 **가스와 다른 도메인 특성에 맞춘 의도된 비대칭**. 외부 리뷰가 "1차 MVP" 로 평가한 6항목 (watt 단독·4채널·window 30·night 30%·1-step ARIMA·un-downgrade) 모두 의도된 스코핑 + 후속 plan 분리 완료. **AI 는 보조, 정적 임계는 베이스라인** 원칙이 quality_guard / DISABLED / WARMING_UP / INFERRED_FAILED / decide_alarm 의 모든 cover 분기에 일관 적용됨.
