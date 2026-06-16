# 전력 5축 정책 엔진 — 데이터 흐름 + 핵심 함수 분석

작성일: 2026-05-19
대상 작업: 브랜치 `feature/power_zscore_cp` 3 commits (D2 / E1 / F)
관련 문서: [`drf-server/docs/refactoring/power-ai-zscore-changepoint-2026-05-19.md`](../../../../drf-server/docs/refactoring/power-ai-zscore-changepoint-2026-05-19.md) — 배경·결정·검증

본 문서는 **"코드가 어떻게 흐르는지"** 와 **"어떤 함수가 핵심인지"** 에 집중. 변경 의도·결정 근거는 위 refactoring 문서 참조.

---

## 1. 범위 — 변경 영역

```
fastapi-server                                drf-server
├── power/services/                           ├── apps/core/
│   ├── power_service.py ★★★ (process_anomaly_inference) │   └── constants.py ★ (ALGORITHM_SOURCE_LABEL 동기)
│   └── change_point_service.py ★★★ (신규)
├── ai/                                       └── apps/alerts/models/
│   └── risk_combine.py ★★ (combine_risk_5axis 추가)        └── alarm_record.py (영향 0 — .get() fallback)
└── tests/
    ├── test_power_service_zscore.py ★ (신규, 6)
    ├── test_change_point_service.py ★ (신규, 6)
    └── test_risk_combine.py ★ (16 추가)
```

★ = 본 작업 변경. 가스 측 파일 0 touch.

---

## 2. 데이터 흐름 (한 추론 틱)

```
[엣지게이트웨이 → POST /api/power/watt]
            │
            ▼
process_power_data (api/routers/power_router.py — 변경 없음)
            │
            ▼
process_anomaly_inference (power_service.py:138)  ◀── ★ 본 작업 핵심
   │
   ├─ (0) classify_sensor_status / is_inference_stuck  ← W0 quality_guard (변경 없음)
   │
   ├─ (1) win.append(value)  ← _power_windows[(ch,data_type)] deque(maxlen=30)
   │     if len(win) < 30: continue
   │
   ├─ (2) IF 추론
   │     score = entry.model.decision_function(row)[0]
   │     prediction = "anomaly" if pred_int == -1 else "normal"
   │
   ├─ (3) D2 — Z-score                              ◀── 신규 (D2 commit)
   │     z_score_anomaly = _zscore_check(win, value, threshold=3.0)
   │
   ├─ (4) E1 — Change Point                         ◀── 신규 (E1 commit)
   │     change_point, cp_meta = detect_change_point((ch, data_type), value)
   │     if change_point: logger.info("[change_point] STABLE→SHIFT mean_shift=... std_ratio=...")
   │
   ├─ (5) W3.2 ARIMA forecast (변경 없음)
   │     arima_violation = _arima_forecast(...)["is_violation"]
   │
   ├─ (6) F — combine_risk_5axis                    ◀── 5축 우선순위 (F commit)
   │     threshold_risk = calculate_power_risk(...)
   │     combined = combine_risk_5axis(
   │         threshold_risk, prediction, arima_violation,
   │         z_score_anomaly, change_point,
   │     )
   │
   ├─ (7) night_abnormal 시각 분기 (변경 없음 — combined 후처리)
   │     if data_type == "watt" and _is_night_kst_iso(measured_at) and watt > 정격 30%:
   │         combined = _NIGHT_ESCALATION.get(combined, combined); night_escalated = True
   │
   ├─ (8) algorithm_source priority (확장 — F commit)  ◀── 6단계 priority
   │     if night_escalated:                        → "night_abnormal"
   │     elif prediction == "anomaly" and arima_violation: → "combined"  (IF+ARIMA)
   │     elif change_point:                         → "change_point"     ★ 신규
   │     elif arima_violation:                      → "arima"
   │     elif z_score_anomaly:                      → "zscore"            ★ 신규
   │     elif prediction == "anomaly":              → "isolation_forest"
   │     else:                                      → ""
   │
   ├─ (9) 로그 보강 (z=/cp= 필드 추가 — D2 + E1)
   │     [anomaly_inference] device=... threshold=... pred=... arima_v=... z=... cp=... combined=... score=...
   │
   └─ (10) forward_inference_e2e  ← AlarmRecord 저장 + push_alarm + ML forward (변경 없음)
          ML payload / alarm_payload / push_payload 안에 algorithm_source 동행
          anomaly_meta payload 안에 z_score_anomaly / change_point / cp_mean_shift / cp_std_ratio 추가 (F)
```

---

## 3. 핵심 함수 — 시그니처 + 동작

### 3.1 `_zscore_check` (D2 + 코드리뷰 §3.1 보강)

```python
# power_service.py:96
def _zscore_check(
    window: deque, value: float, threshold: float = 3.0
) -> tuple[bool, float]:  # ← 코드리뷰 §3.1: bool → (bool, z) 변경
    if len(window) < _INFERENCE_WINDOW:  # 30
        return False, 0.0
    arr = np.array(window, dtype=float)
    z = abs(value - arr.mean()) / (arr.std() + 1e-9)
    return bool(z >= threshold), float(z)
```

**입력**: IF 추론 윈도우 (이미 value append 된 상태) + 현재 값 + 임계.
**출력**: `(is_anomaly, z)` 튜플
- `is_anomaly` — Python bool (numpy bool 캐스팅 — `is True/False` 검증 호환).
- `z` — 실제 |z| 값 (로깅용). 윈도우 미충족 시 0.0.

**EPS=1e-9**: std=0 (완전 동일값) 분모 폭발 안전핀. 실제 운영에선 quality_guard.is_inference_stuck 이 해당 케이스 사전 차단 — EPS 는 방어선.

**호출 위치**: `process_anomaly_inference` L227, IF 추론 직후·ARIMA 분기 전. fire 시 dedicated 로그:

```
[zscore] device=63200c3afd12 ch=1 watt value=5341.0 |z|=4.17 >= 3.0
```

(코드리뷰 §3.1 — Z-score 발화 시점 가시성 보강. CP fire 로그와 패턴 통일.)

---

### 3.2 `detect_change_point` (E1)

```python
# change_point_service.py:40
def detect_change_point(key: tuple[int, str], value: float) -> tuple[bool, dict]:
    win = _cp_windows[key]      # deque(maxlen=60), 별도 윈도우 (IF 30 과 분리)
    win.append(value)
    if len(win) < 60: return False, {}

    arr = np.array(win, dtype=float)
    prev = arr[:30]; curr = arr[30:]
    mean_shift = abs(curr.mean() - prev.mean()) / (prev.std() + 1e-9)
    std_ratio = (curr.std() + 1e-9) / (prev.std() + 1e-9)
    is_change = (mean_shift >= 3.0) or (std_ratio >= 2.0) or (std_ratio <= 0.5)

    prev_state = _cp_states[key]
    is_change_point = False
    if prev_state == "STABLE" and is_change:
        _cp_states[key] = "SHIFT"; is_change_point = True
    elif prev_state == "SHIFT" and not is_change:
        _cp_states[key] = "STABLE"  # silent BACK_TO_STABLE
    return is_change_point, {"mean_shift": ..., "std_ratio": ..., "state": ...}
```

**상태 머신**:

```
        is_change=True               not is_change
STABLE ────────────────►  SHIFT  ────────────────►  STABLE
       (fire CHANGE_POINT)         (silent BACK_TO_STABLE)
                  ▲                       │
                  └─ is_change=True ──────┘  (SHIFT 지속, fire X)
                     (fire X)
```

**핵심**: fire 는 **STABLE → SHIFT 전이 시점만**. SHIFT 지속 중 / BACK_TO_STABLE 시 silent → 중복 발화 방지.

**별도 윈도우 이유**: IF 윈도우 (30) 와 CP 윈도우 (60) 길이 다름. 통합 시 IF startup 2배 (30→60틱) + 두 알고리즘이 같은 deque 공유 시 의도 불투명. 별도 deque + 별도 dict state = 추론 흐름에 영향 0.

**호출 위치**: `process_anomaly_inference` L234, Z-score 직후. fire 시 별도 logger.info (night_abnormal fire 로그 패턴 일관).

---

### 3.3 `combine_risk_5axis` (F + 코드리뷰 §2.1 보강)

```python
# ai/risk_combine.py:118
def combine_risk_5axis(
    threshold_risk: str, if_prediction: str, arima_violation: bool,
    z_score_anomaly: bool, change_point: bool,
) -> tuple[str, str]:  # ← 코드리뷰 §2.1: str → (combined, escalation_source)
    base = combine_risk_3axis(threshold_risk, if_prediction, arima_violation)
    if base != "normal":
        return base, ""                          # ← z/cp 격상 기여 X
    if change_point:                             # ← z+cp 둘 다 True 면 CP 우선
        return "predict_warn", "change_point"
    if z_score_anomaly:
        return "predict_warn", "zscore"
    return "normal", ""
```

**STEP 5 우선순위 매핑**:

| 우선순위 | 조건 | combined_risk | escalation_source |
|---|---|---|---|
| 1 CRITICAL | threshold danger | "danger" | "" |
| 2 ML_ANOMALY (강함) | IF anomaly + ARIMA viol | "warning"/"danger" (3축 격상) | "" |
| 2 ML_ANOMALY | IF anomaly | base (3축) | "" |
| 3 ANOMALY_WARNING | Z-score, base==normal | "predict_warn" | **"zscore"** |
| 4 TREND_SHIFT | CP, base==normal | "predict_warn" | **"change_point"** |
| 5 PREDICTIVE_ALERT | ARIMA viol 단독 | base (3축 = predict_warn) | "" |
| 6 NORMAL | 모두 False | "normal" | "" |

**base 위임 의의** — `combine_risk_3axis` 의 12-cell 매트릭스 결과를 그대로 반환 (base != "normal" 분기). Z-score / CP=F 일 때 5축 == 3축 (회귀 가드). 두 AI 동의 격상 의도 (IF anomaly + ARIMA True → 한 단계 격상) 도 자동 보존.

**escalation_source 의의 (코드리뷰 §2.1)** — "z/cp 가 실제 risk 격상에 기여했는가" 를 caller 에 명시.
- base != "normal" 이면 z/cp 발생해도 ""—그 신호는 차후 별도 통계로만 기록 (`anomaly_meta.z_score_anomaly` 등 payload 필드), 라벨로는 사용 X.
- base == "normal" 일 때만 zscore/change_point 라벨 — 실제 격상 driver 일치 보장.
- z + cp 둘 다 True 시 change_point 우선 (algorithm_source priority 일관성).

이 정보로 caller (`process_anomaly_inference`) 는 `algorithm_source` 결정 시 "라벨이 실제 driver 와 일치" 보장. 보강 전엔 `elif change_point: → "change_point"` 가 base 무관하게 매칭됐고, threshold=danger+cp=True 시 라벨 "급변" + combined=danger 의 misleading 조합 발생 가능했음 (코드리뷰 §2.1 보강 전 문제).

---

## 4. algorithm_source priority 변화 (F + 코드리뷰 §2.1 보강)

```python
# power_service.py:303-322 (코드리뷰 보강 후)
if night_escalated:
    algorithm_source = "night_abnormal"
elif prediction == "anomaly" and arima_violation:
    algorithm_source = "combined"                       # IF + ARIMA
elif escalation_source == "change_point":               # ← §2.1 보강
    algorithm_source = "change_point"
elif arima_violation:
    algorithm_source = "arima"
elif escalation_source == "zscore":                     # ← §2.1 보강
    algorithm_source = "zscore"
elif prediction == "anomaly":
    algorithm_source = "isolation_forest"
else:
    algorithm_source = ""
```

| 조건 | W4.a (기존) | F (초기) | F + §2.1 보강 |
|---|---|---|---|
| night_abnormal 격상 | night_abnormal | night_abnormal | night_abnormal |
| IF anomaly + ARIMA viol | combined | combined | combined |
| CP True | (없음) | change_point | **escalation_source == "change_point" 일 때만** ★ |
| ARIMA viol 단독 | arima | arima | arima |
| Z-score True | (없음) | zscore | **escalation_source == "zscore" 일 때만** ★ |
| IF anomaly 단독 | isolation_forest | isolation_forest | isolation_forest |
| 없음 (threshold 단독 발화 등) | "" | "" | "" |

★ F 초기 → §2.1 보강 차이: 보강 전엔 `elif change_point: → "change_point"` 가 base 결과 무관하게 매칭. 보강 후엔 `combine_risk_5axis` 가 반환하는 `escalation_source` 값 일치 시만 매칭 → 라벨이 실제 격상 driver 와 일치.

**우선순위 근거**:
- TREND_SHIFT (CP) > PREDICTIVE_ALERT (ARIMA) — CP 는 "이미 발생한 상태 변화 시점 확정", ARIMA 는 "미래 가능성 예측". 운영 대응 시급도 ↑.
- Z-score > IF? **반대**. IF (4피처 다변량 + 학습 분포) > Z-score (단변량 통계). priority 에서 zscore 가 IF 보다 위에 있는 건 "둘 다 발화 시 zscore 가 더 explainable" — 운영자에게 "평소보다 N σ 튐" 이 "ML 학습 분포 밖" 보다 직관. **운영자 친화 우선**.

---

## 5. 시나리오별 발화 경로 (라이브 검증 결과 — refactoring 문서 §검증 결과 참조)

### overload (단발 spike 8000W+, 정격 7500W)
```
threshold=danger pred=anomaly arima_v=False z=False cp=False
→ combine_risk_5axis → base=danger → return base ("danger")
→ algorithm_source = "combined" (prediction=anomaly + arima_v=False 라 → 그 다음 elif)
  ❗ 정확히는: arima_v=False 라 "combined" 아니라 "isolation_forest"
→ UI 토스트: "[IF 이상 감지] CH1 watt=8110.9 ..."
```

### degradation 초기 (점진 부하 ↑, value 5341W, 정격 7500W = 71%)
```
threshold=normal pred=normal arima_v=False z=True cp=False
→ combine_risk_5axis → base=normal + z=True → ("predict_warn", "zscore")
→ algorithm_source = "zscore" (escalation_source == "zscore" 매칭)
→ UI 토스트: "[Z-score 이상 감지] CH1 watt=5341 ..."
→ logger.info("[zscore] device=... value=5341 |z|=4.17 >= 3.0")
```

### degradation 중기 (value 6726W, 정격 89%) — 코드리뷰 §2.1 보강의 핵심 케이스
```
threshold=warning pred=normal arima_v=False z=True cp=False
→ combine_risk_5axis → base=caution + z=True → ("caution", "")
                                                          ↑
                                       z 격상 기여 X (base != normal)
→ algorithm_source 결정:
   • F 초기 (보강 전): elif z_score_anomaly: → "zscore" ❌ misleading
                       UI: "[Z-score 이상 감지] caution" — 운영자가 z 가 driver 라 오인
   • F + §2.1 보강:   elif escalation_source == "zscore": (False) → 다음 elif
                       elif prediction == "anomaly": (False) → ""
                       UI: "[AI] caution" — fallback 라벨, 실제 driver(threshold) 와 일치
```

### degradation 후반 (60s+ 점진 ↑ 후 CP 발화) — 보강 후 동작
```
threshold=warning pred=normal arima_v=False z=True cp=True
→ combine_risk_5axis → base=caution + z=True, cp=True → ("caution", "")
                                                                  ↑
                                              z/cp 둘 다 격상 기여 X (base != normal)
→ algorithm_source = "" (모든 elif 매칭 X — fallback "AI")
→ logger.info("[change_point] device=... STABLE->SHIFT mean_shift=... std_ratio=...")
   (CP fire 자체는 별도 dedicated 로그에 기록 — UI 라벨과 별개)
→ UI 토스트: "[AI] caution (combined=caution)"
```

→ 운영자가 라벨 misleading 없이 정확히 "현재 위험은 threshold=warning 기반 caution" 으로 해석. CP fire 는 별도 INFO 로그로 추적 가능.

### night_abnormal (KST 22~05, watt > 정격 30%)
```
combined_5axis 결과 (예: caution) → night_abnormal 시각 분기 한 단계 격상 (caution → warning)
→ night_escalated = True
→ algorithm_source = "night_abnormal" (최상위 priority)
```

---

## 6. 회귀 가드 정리

| 회귀 위험 | 가드 |
|---|---|
| W3.1 3축 매트릭스 12-cell | `combine_risk_5axis` base 위임 — Z-score/CP=F 일 때 5축 == 3축. test_combine_risk_5axis_preserves_3axis_regression 가 12 × 2 조합 검증 |
| 두 AI 동의 격상 (IF anomaly + ARIMA True → 한 단계 격상) | base 통과 그대로 — test_combine_risk_3axis_two_ai_agreement_escalates 보존 |
| 기존 algorithm_source 결과 (night/combined/arima/IF) | F priority 신규 항목 (change_point/zscore) 은 기존 조건과 mutually exclusive. CP/Z-score=False 시 기존 priority 그대로 |
| 가스 측 process_gas_data | 0 touch — combine_risk_3axis import 도 가스 측엔 영향 없음 (가스는 다른 combine_risk 사용) |
| _INFERENCE_ENABLED_CHANNELS = {(1, "watt")} | 변경 없음 — 활성 채널만 5축 적용. 다른 채널 영향 0 |
| 기존 anomaly_meta 필드 (combined_risk, anomaly_score, arima_forecast, ...) | 신규 필드 4개 (z_score_anomaly/change_point/cp_mean_shift/cp_std_ratio) 추가만, 기존 필드 0 변경 — UI 측 회귀 0 |

전체 fastapi 회귀: 172/172 통과 (기존 156 + 신규 16).

---

## 7. 학습 시연 가치

- **base 위임 패턴** — 신규 매트릭스 직접 정의 대신 기존 매트릭스를 base 로 호출. 회귀 가드 자동.
- **우선순위 함수 (if/elif)** — N 축이 5 이상일 때 full matrix 보다 우선순위 함수가 유지·이해 비용 ↓. STEP 5 권고의 우선순위 매트릭스를 코드 구조로 명시화.
- **상태 머신 (STABLE↔SHIFT)** — 점진 변화 1회만 발화. 중복 발화·운영자 피로 방지. CP 같은 "패턴 변화 감지" 알고리즘의 일반 패턴.
- **윈도우 분리 원칙** — 길이 다른 두 통계의 윈도우는 분리. 알고리즘 독립성 확보.
- **단일 진실 공급원 (SoT) 동기** — `_ALGORITHM_SOURCE_LABEL` (fastapi) ↔ `ALGORITHM_SOURCE_LABEL` (DRF constants) 양쪽 dict 동시 갱신. 한 쪽만 바뀌면 토스트 라벨 / DB 라벨 불일치.
- **라벨과 위험도 결정의 분리** (코드리뷰 §2.1 보강) — `combined_risk` (위험도 수치) 와 `algorithm_source` (어떤 AI 가 발화 driver) 는 의미가 다름. 라벨링 책임을 위험도 결정 함수 (`combine_risk_5axis`) 가 함께 안고 caller 에 명시 (`escalation_source` 반환) → 라벨 misleading 방지.
- **함수 시그니처로 "함수가 알고 있는 정보" 외부 명시** — 보강 전 `combine_risk_5axis` 는 결과만 반환하고 라벨 결정 책임은 caller (`process_anomaly_inference`) 에 떠넘김. 보강 후 함수가 "base 가 driver 인가 / z·cp 가 driver 인가" 정보를 직접 반환 → caller 의 로직 간단화 + 의도 명시.
- **로그 가시성 비대칭의 비용** (코드리뷰 §3.1 보강) — 한 알고리즘(CP) 만 dedicated fire 로그를 두면 다른 알고리즘(Z-score) 의 발화 추적이 운영자에게 비용 ↑. 패턴 통일이 운영 분석 비용 ↓.
- **테스트 격리 책임의 모듈화** (코드리뷰 §3.3 보강) — module-level mutable state 가 있는 모듈은 `reset_state()` 같은 public 헬퍼 제공. 테스트 파일이 private 필드에 의존하지 않게 캡슐화.
