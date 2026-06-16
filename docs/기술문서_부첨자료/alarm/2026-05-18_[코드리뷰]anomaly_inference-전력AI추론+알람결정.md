## `anomaly_inference.py` — 전력 채널별 AI 추론 + 알람 결정 (핵심 파일)

이 파일이 전력 AI 파이프라인의 **실제 실행 지점**입니다. 채널별로 5축(IF/ARIMA/Z-score/Change Point/정적 임계) 을 결합해 단일 알람 결정을 내립니다. T4 plan 의 "fastapi 단일 결정자" 정책이 본 파일에서 구현됩니다.

가스의 `gas_service.py` 와 동등한 위치이지만, 가스는 3가지 (IF + ARIMA + 정적) 인 반면 전력은 5축 + AI 5 state + source 6 매트릭스로 복잡도가 한 차원 높습니다.

---

### 전체 구조 한눈에 보기

```
process_anomaly_inference(device_id, channel_values, data_type, measured_at, ingress_ts)
    └─ for each channel:
        ├─ [1] quality_guard — comm_failure/overflow → skip (state 마킹 X)
        ├─ [2] 정적 평가 — evaluate_static_risk_from_cache (모든 채널 공통)
        ├─ [3] AI 비활성 채널 (ch 1/9/14/15 외) → DISABLED
        │       └─ decide_alarm → static_no_ai_available (static fired 시만)
        ├─ [4] 윈도우 < 30 → WARMING_UP
        │       └─ decide_alarm → static_cover_warmup
        ├─ [5] is_inference_stuck → skip (값 30개 동일 = 센서 고정 고장)
        ├─ [6] AI 추론 5축 결합:
        │       · IF        (Isolation Forest, decision_function + predict)
        │       · ARIMA     (forecast + CI violation)
        │       · Z-score   (window 통계 ± 3σ)
        │       · CP        (two-window mean_shift/std_ratio)
        │       · threshold (정적 임계 risk)
        │       → combine_risk_5axis() → combined ∈ {normal/caution/predict_warn/warning/danger}
        ├─ [7] night_escalation — KST 야간 + watt > rated 30% → 한 단계 격상
        ├─ [8] algorithm_source 결정 (night > combined > cp > arima > zscore > if)
        ├─ [9] combined ∈ FIRE_LEVELS → rate limit 60s 체크 → FIRED, else INFERRED_NORMAL
        ├─ [10] decide_alarm → AlarmDecision (source 6종)
        └─ [11] push_alarm (Redis 큐) + forward_inference_e2e (DRF ML/Alarm 영속화)

    예외 시: INFERRED_FAILED 마킹 + 정적 폴백 (static_cover_inference_fail)
```

---

### 왜 5축 결합인가

**선택**: IF / ARIMA / Z-score / Change Point / 정적 임계 — 5개 독립 신호를 한 함수 `combine_risk_5axis` 로 묶음.

**배경**: STEP 4 권고에 따라 도메인별 특성을 잡기 위함.
- IF: 다변량 분포 이상 (학습 데이터 외 영역)
- ARIMA: 시계열 패턴 위반 (forecast CI 밖)
- Z-score: 슬라이딩 윈도우 통계 이상 (±3σ)
- Change Point: 두 윈도우 평균/분산 비교 (시점 자체의 변화)
- 정적 임계: 절대값 룰 (운영자 설정 정격 %)

```python
combined, escalation_source = combine_risk_5axis(
    threshold_risk, prediction, arima_violation, z_score_anomaly, change_point
)
```

5축은 동등하지 않습니다 — base 3축 (threshold/IF/ARIMA) 가 combined 를 결정하고, Z/CP 는 base=normal 일 때만 `predict_warn` 으로 격상하는 보조축입니다. `escalation_source` 가 격상에 기여한 축 라벨.

**트레이드오프**:
- ↑ **단일 축 실패 보호** — IF 모델이 학습 부족이어도 ARIMA/threshold 가 잡음. 다축 중 어느 하나가 발화하면 알람.
- ↑ **알람 라벨 풍부** — `algorithm_source` 로 어떤 축이 발화시켰는지 운영자에게 노출 ("이상 수치 탐지" vs "패턴 변화 탐지" vs "야간 가동").
- ↓ **결합 로직 복잡** — `combine_risk_5axis` 의 우선순위 규칙이 코드 외부 (`ai/risk_combine.py`) 에 있어 본 파일만 읽어서는 결정 흐름 추적 불가. 디버깅 시 두 파일을 같이 봐야 함.
- ↓ **5축 모두 동의 안 해도 발화** — base=warning 한 축만 잡혀도 combined=warning. 위양성률 (false positive) 이 단축 대비 높음. 시연 환경에서는 가시성↑ 가치가 더 크지만, 실제 운영에서는 운영자 알람 피로 가능.
- ↓ **Z/CP 가 base 미발화 시만 작동** — base=warning 이면 Z/CP 발화해도 라벨이 안 바뀜. Z/CP 가 실제로는 더 중요한 신호일 때도 가려질 수 있음.

---

### 왜 ch1/9/14/15 + watt 만 AI 활성인가

**선택**: 16채널 중 4채널, 측정종 3종 중 watt 만 AI 추론 대상.

```python
_INFERENCE_ENABLED_CHANNELS: set[tuple[int, str]] = {
    (1, "watt"),    # 압연기 — 모터성 부하 대표
    (9, "watt"),    # 메인 전력반 — 전체 부하 합성
    (14, "watt"),   # 공조 — 주기성 부하
    (15, "watt"),   # 조명 — 시간대 패턴 명확
}
```

**배경**: 부하 프로파일 다양성 검증을 위한 의도적 선정 (skill/memory `power_ai_un_downgrade_phase2_apply_2026_05_18`).
- ch1 (압연기): 정격 7.5kW 모터 — overload/motor_stuck 시연
- ch9 (메인 전력반): 정격 15kW — 합성 부하 추세
- ch14 (공조): 정격 5.5kW — 주기성
- ch15 (조명): 정격 1kW — 야간 가동 시연

**트레이드오프**:
- ↑ **학습 자원 효율** — 16채널 × 3종 = 48 모델 학습 대신 4 모델. ARIMA fit 시간 절약 (10000 rows × 16 = 무거움).
- ↑ **시연 신뢰성** — 검증된 4채널만 발화 → 시연 중 예측 못 한 채널 발화 위험 0.
- ↓ **운영 전환 시 확장 필요** — 16채널 전체 운영 시 ch2/3/4/5/6/7/8/12/13 의 12채널은 AI 미보호. 정적 임계만 작동 (Source: `static_no_ai_available`).
- ↓ **current/voltage 누락** — watt 만 학습. 전류 단독 이상 (정격 110% A + 정상 W, motor starting current 같은 케이스) 은 탐지 불가. T4 D1a `channel_meta_cache` 정적 검증으로 일부 커버.
- ↓ **하드코딩 set** — DRF 어드민에서 채널별 AI on/off 토글 불가. 코드 수정 + fastapi 재시작 필요.

---

### 왜 ML forward 는 항상, push 는 rate limited 인가

**선택**: 추론 결과 (MLAnomalyResult) 는 매번 DRF 에 저장, 브라우저 push (push_alarm) + AlarmRecord 영속화는 60초당 1회.

```python
if combined in _FIRE_LEVELS:
    now_ts = time.time()
    if now_ts - last_ts < RATE_LIMIT_SEC:
        POWER_AI_RATE_LIMITED_TOTAL.inc()
        asyncio.create_task(forward_inference_e2e(ml_payload, None))  # ML only
        continue
    _last_fired_at[sensor_identifier] = now_ts
    # ... full push 진행
```

**배경**: 운영 추적 (ML forward) 과 사용자 UX (브라우저 팝업) 의 분리.
- 운영 측: "ch1 에서 30초간 이상이 몇 번 잡혔는가" — 분석에 모든 추론 결과 필요.
- 사용자 측: 1초마다 팝업 띄우면 알람 피로 → 60초 1회로 throttle.

**트레이드오프**:
- ↑ **분석 풍부** — `MLAnomalyResult` 에 모든 추론이 저장되어 사후 IF 재학습·threshold 튜닝 데이터 충분.
- ↑ **운영자 UX 보호** — 한 채널이 1분 내 60틱 발화해도 팝업 1회 + AlarmRecord 1건. 시연 중 알람 폭주 회피.
- ↓ **rate limit 메모리 휘발** — `_last_fired_at` 이 프로세스 메모리 dict. fastapi 재시작 직후 60초 안에 같은 채널 발화 시 직전 발화 시각 잊고 다시 발화. 재시작 직후 중복 알람 가능.
- ↓ **AlarmRecord 누락 위험** — rate limit 통과 못 한 발화는 AlarmRecord 미생성. "이 시각에 발화했는데 왜 DB 에 없냐" — 운영자 혼란 가능. ML 결과만 보면 알 수 있지만 동선이 분리됨.
- ↓ **rate limit 키가 sensor_identifier 단위** — `power:device_{mac}:ch{n}:{type}` 단위라 같은 디바이스의 ch1/ch9 가 동시에 발화하면 둘 다 통과. 디바이스 전체 throttle 은 안 됨.

---

### 왜 INFERRED_FAILED 에 정적 폴백을 두는가

**선택**: AI 추론 예외 시 `INFERRED_FAILED` 마킹 + 정적 평가 결과로 알람 결정.

```python
except Exception as exc:
    AI_INFERENCE_FAILED_TOTAL.labels("power_if", "inference_error").inc()
    try:
        await mark_ai_state(device_id, channel, data_type, AIInferenceState.INFERRED_FAILED)
        decision = decide_alarm(
            AIInferenceState.INFERRED_FAILED, "normal", static_risk
        )
        if decision is not None:
            await _push_static_decision(...)
    except Exception:
        logger.exception("[anomaly_inference] inference-failed fallback failed")
```

**배경**: T4 sub-plan 의 "AI 가 결정 못 하더라도 정적 임계는 무조건 작동" — 안전망. 모델 파일 누락/scikit-learn 버전 충돌/메모리 부족 등 어떤 이유로 추론이 실패해도 정적 평가는 동작해야 함.

**트레이드오프**:
- ↑ **무조건 안전망** — 어떤 추론 실패 (sklearn import 에러, ARIMA pkl 파손 등) 에도 정적 임계는 작동. 운영자가 "AI 가 죽었는데 알람도 안 옴" 상황 회피.
- ↑ **분석 가능** — Prometheus `AI_INFERENCE_FAILED_TOTAL{reason=...}` 으로 실패 종류·빈도 추적.
- ↓ **실패 마스킹** — 자주 INFERRED_FAILED 가 되어도 정적이 덮어서 사용자에게는 "정상 작동" 처럼 보임. 실제로는 AI 가 죽어 있는 상태. Grafana 알림이 없으면 발견 어려움.
- ↓ **source 라벨 의미 모호** — `static_cover_inference_fail` 이라는 source 가 알람에 붙어도 운영자가 어떤 조치를 해야 하는지 불명 (개발자 호출? 무시?). 운영자용 가이드가 필요.

---

### 왜 night_escalation 이 watt 한정인가

**선택**: KST 야간 + watt > 정격 30% 일 때만 한 단계 격상 (caution → warning, warning → danger).

```python
if data_type == "watt" and _is_night_kst_iso(measured_at):
    rated_w = entry_meta.get("rated_w")
    if rated_w is not None and value > float(rated_w) * _NIGHT_THRESHOLD_RATIO:
        escalated = _NIGHT_ESCALATION.get(combined, combined)
        if escalated != combined:
            combined = escalated
            night_escalated = True
```

**배경**: 야간 무인 시간대에는 같은 부하라도 의심도가 높음 ("야간에 압연기가 돌고 있다 = 의도된 작업 아님 가능성"). watt 가 가장 직접적 신호 — current/voltage 단독으로는 "가동 중" 판단이 약함.

**트레이드오프**:
- ↑ **도메인 지식 반영** — 같은 수치라도 시각 가중치를 둠. 운영자 직관과 일치.
- ↑ **algorithm_source="night_abnormal" 라벨** — 운영자에게 "야간 가동 의심" 으로 명확 전달.
- ↓ **current 단독 이상 누락** — 야간에 W 정상 + A 만 비정상 (전동기 베어링 손상 초기 신호) 은 격상 안 됨. 도메인 지식상 가치 있는 신호인지 결정 보류 상태.
- ↓ **정격 30% 임계 하드코딩** — `_NIGHT_THRESHOLD_RATIO` 가 모듈 상수. 어드민에서 조정 불가. 채널별로 야간 baseline 이 달라야 (예: ch15 조명은 야간에도 30% 정상) 하는데 일률 적용.
- ↓ **KST 가정** — `_is_night_kst_iso` 는 한국 시간대 하드코딩. 해외 배포 시 measured_at 의 timezone offset 무관 KST 22~06 시 사용. 다중 시간대 운영 불가.

---

### 왜 algorithm_source 우선순위가 night > combined > cp > arima > zscore > if 인가

**선택**: 한 발화에 여러 축이 동시 기여해도 단일 라벨만 노출.

```python
if night_escalated:                              algorithm_source = "night_abnormal"
elif prediction == "anomaly" and arima_violation: algorithm_source = "combined"
elif escalation_source == "change_point":         algorithm_source = "change_point"
elif arima_violation:                             algorithm_source = "arima"
elif escalation_source == "zscore":               algorithm_source = "zscore"
elif prediction == "anomaly":                     algorithm_source = "isolation_forest"
else:                                             algorithm_source = ""
```

**배경**: 운영자가 한 알람에서 한 라벨만 보게 함 — 알람 모달의 "원인" 슬롯이 1개. "이상 수치·패턴 동시 탐지" (`combined`) 가 가장 강한 신호이고, night 은 도메인 가중치라 더 위.

`escalation_source == "change_point"` 가 `arima_violation` 보다 위인 이유는 CP 가 base 미발화 시만 작동 — CP 가 라벨로 채택되는 건 IF/ARIMA 가 못 잡았다는 의미, 그게 더 운영자에게 흥미로움.

**트레이드오프**:
- ↑ **운영자 가독성** — 한 라벨만 모달에 표시. "왜 발화했나" 단일 답.
- ↑ **escalation_source 가드** — Z/CP 는 escalation 으로 기여했을 때만 라벨에 채택 (base 가 IF 라벨인데 우연히 CP 도 발화하면 라벨 충돌 회피).
- ↓ **다축 동시 발화 정보 손실** — IF + ARIMA + CP 가 모두 발화해도 라벨은 "combined" 한 줄. 어느 축이 얼마나 강했는지는 `MLAnomalyResult.feature_snapshot_json` 봐야 함.
- ↓ **POWER_AI_AXIS_FIRED_TOTAL 카운터와 라벨 불일치** — counter 는 발화한 모든 축에 1씩 증가하지만 라벨은 1개. Grafana 비율 분석 시 "라벨=arima" 인 케이스가 실제로는 IF 도 같이 발화했다는 점 놓침.

---

### 왜 source=ai vs source=static_* 두 분기를 두는가

**선택**: AI 발화는 AlarmRecord 영속화 (DB 보존), 정적 cover 는 push 만 (휘발).

```python
if decision.source == "ai":
    alarm_payload = {...}  # forward_inference_e2e 가 AlarmRecord 생성
else:
    alarm_payload = None   # push 만, AlarmRecord 없음
```

**배경**: T4 D2 매트릭스 (decide_alarm.py 참조).
- AI 발화 = "확신 있는 이상" → 사후 분석/리포트용 영구 기록
- 정적 cover (static_cover_miss/warmup/fail) = "AI 가 못 잡았거나 못 잡는 상황의 백업 알람" → 일시적 알림, 영구 기록 불요

**트레이드오프**:
- ↑ **DB 부담 분리** — 정적이 빈번히 발화하는 채널 (AI 비활성 12채널) 의 AlarmRecord 폭증 회피.
- ↑ **분석 데이터 품질** — AlarmRecord 가 AI 결과만 보유 → 사후 모델 평가 (precision/recall) 시 ground truth 와 비교 용이.
- ↓ **운영자 이력 누락** — 정적 cover 로 발화한 알람은 브라우저에 떴다가 사라지면 DB 에 흔적 없음. "어제 밤에 알람이 떴는데 뭐였더라" 추적 불가.
- ↓ **source 6 매트릭스 의도가 코드에서 안 보임** — `decide_alarm.py` 가 source 결정만, AlarmRecord 분기는 본 파일에서. 매트릭스가 두 파일에 걸쳐 있음.

---

### 왜 _last_fired_at / _power_windows / _cp_windows 가 모듈 전역인가

**선택**: 세 dict 모두 모듈 단위 (`dict[(channel, data_type), deque]`).

**배경**: 단일 fastapi 프로세스 가정. asyncio 동시성이지만 같은 이벤트 루프 — 동시 mutate 없음. Redis/외부 큐 없이 zero-cost.

**트레이드오프**:
- ↑ **추론 지연 0** — 외부 호출 없이 dict access. 1Hz 환경 적합.
- ↑ **인프라 단순** — Redis pub/sub 없음.
- ↓ **재시작 시 손실** — `_last_fired_at` (rate limit), `_power_windows` (IF 입력 30개), `_cp_windows` (CP 입력 60개) 모두 초기화. 재시작 직후 30~60초간 워밍업 (`WARMING_UP` 마킹) → AI 알람 없음. 그동안 정적 임계만 작동.
- ↓ **다중 worker 불가** — 채널별 윈도우가 worker 별로 분기됨. ch1 측정값이 worker A 에 가고 ch9 가 worker B 에 가면 윈도우 누적이 분산되어 발화 조건 못 채움.
- ↓ **메모리 무한 증가 잠재** — `_last_fired_at` 은 dict, 새 sensor_identifier 가 등장할 때마다 키 추가. cleanup 없음. 디바이스 다수 환경에서는 메모리 증가 신호 모니터링 필요.

---

### 왜 추론 흐름이 한 함수에 250 줄로 묶여 있는가

**선택**: `process_anomaly_inference` 한 함수에 quality_guard / 정적 평가 / state 마킹 / 5축 추론 / decide_alarm / push / forward 가 모두 들어 있음.

**배경**: T4 D2 plan 시점에서 우선 동작 확보. 분할은 후속 작업으로 미룸 (시연 우선).

**트레이드오프**:
- ↑ **흐름 한눈에** — 채널 하나가 들어와서 알람이 나갈 때까지 한 함수에서 추적 가능. 디버깅 시 다른 파일로 점프 불요.
- ↑ **state 마킹 시점이 명확** — DISABLED/WARMING_UP/FIRED/INFERRED_NORMAL/INFERRED_FAILED 5종이 같은 함수에서 분기별로 호출 — 누락 위험 낮음.
- ↓ **단위 테스트 어려움** — "ch1 + IF anomaly + ARIMA normal + Z fire + CP normal" 조합 테스트 시 외부 의존 (DRF channel-meta, ai.router._get_or_load, Redis) 다 mock 필요. 분할되어 있으면 combine_risk_5axis 만 단독 테스트 가능.
- ↓ **코드 변경 시 영향 범위 큼** — night_escalation 임계만 바꿔도 본 함수의 250 줄 안을 수정. PR 리뷰 시 변경 라인 식별 어려움.
- ↓ **decide_alarm 가 두 번 호출** — DISABLED/WARMING_UP/INFERRED_FAILED 분기에서 한 번, AI 추론 성공 후 한 번. 분기마다 같은 함수 호출 패턴 반복 → DRY 위반.

시연 후 정비 후보: ① 채널 단위 처리를 별도 함수 (`process_single_channel`) 로 분리, ② 5축 추론을 `compute_axes()` 헬퍼로 추출 → push 결정 로직과 분리.
