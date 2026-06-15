# Power AI 다채널 활성화 (ch1 → +ch9/ch14/ch15)

> **작업일**: 2026-05-21
> **plan**: [skill/plan/power-ai-multichannel-activate.md](../../../../skill/plan/power-ai-multichannel-activate.md)
> **트리거**: 사용자 질문 — "1 디바이스 × 1 채널 추론 상태에서 의미있는 모니터링·향후 방향 결정을 위해 몇 개 채널까지 확장해야 하는가"
> **결론**: 4채널 (ch1·ch9·ch14·ch15) 활성화 + 외부 리뷰어 #1 (a/c path 충돌) 본체 해결 + ARIMA fit 본질 보강

---

## 1. 작업 배경

전력 AI 추론은 그동안 디바이스 `63200c3afd12` × ch1 (압연기, 7.5kW 모터) **한 채널만 활성**이었다.
이 상태로는 "모델이 이 채널 한 개에만 운 좋게 맞는지" vs "부하 패턴이 다른 채널에서도 작동하는지" 판단할 근거가 없어,
시연 후 [[demo_2026_06_14_arima_roadmap]] D+30 un-downgrade 정식 적용 결정에도 활용 불가했다.

부하 종류 다양성 기준으로 **ch9 (메인 전력반 15kW 3상) / ch14 (공조 5.5kW) / ch15 (조명 1kW 220V)** 3채널을 추가 활성화.

---

## 2. 변경 사항 (시그니처·동작 기준)

### 2.1 fastapi 활성화 플래그 확장

**Before** ([fastapi-server/power/services/power_service.py:75](../../../../fastapi-server/power/services/power_service.py#L75))
```python
_INFERENCE_ENABLED_CHANNELS: set[tuple[int, str]] = {(1, "watt")}
```

**After**
```python
_INFERENCE_ENABLED_CHANNELS: set[tuple[int, str]] = {
    (1, "watt"), (9, "watt"), (14, "watt"), (15, "watt"),
}
```

→ 4채널 (디바이스 `63200c3afd12`) IF+ARIMA 추론 분기 진입. 다른 채널·data_type 은 종전대로 정적 임계만.

### 2.2 IF 학습 명령 sensor_identifier mac 변환 (회귀 #1 수정)

**Before** ([drf-server/apps/ml/management/commands/train_anomaly_model.py:258](../../../../drf-server/apps/ml/management/commands/train_anomaly_model.py#L258))
```python
sensor_identifier = (
    f"power:device_{opts['device_id']}"  # ← PowerDevice.id (정수) 그대로
    f":ch{opts['channel']}:{opts['data_type']}"
)
```

**After**
```python
device_obj = PowerDevice.objects.get(pk=opts["device_id"])  # PK → raw mac 변환
sensor_identifier = (
    f"power:device_{device_obj.device_id}"
    f":ch{opts['channel']}:{opts['data_type']}"
)
```

→ ARIMA 학습 명령 ([train_arima_power_model.py:96-104](../../../../drf-server/apps/ml/management/commands/train_arima_power_model.py#L96-L104)) 이 이미 사용 중이던 PK→mac 변환 패턴을 IF 명령에도 동일하게 이식.

**왜 회귀였나**: 추론 측 ([power_service.py:367](../../../../fastapi-server/power/services/power_service.py#L367)) 은 `f"power:device_{device_id}:ch{n}:{type}"` 에서 device_id 를 **raw mac** 으로 받음. 두 학습 명령이 표기를 다르게 만들면 IF 모델은 매칭 실패 → 404 silent fallback → IF 미동작.

### 2.3 DRF RiskClassified enum 에 WARNING 추가 (회귀 #2 본체)

**Before** ([drf-server/apps/ml/models/ml_anomaly_result.py:17](../../../../drf-server/apps/ml/models/ml_anomaly_result.py#L17))
```python
class RiskClassified(models.TextChoices):
    NORMAL = "normal", "정상"
    CAUTION = "caution", "주의"
    PREDICT_WARN = "predict_warn", "예측경고"
    DANGER = "danger", "위험"  # ← 4단계
```

**After** (+ migration `0003_alter_mlanomalyresult_risk_classified.py`)
```python
class RiskClassified(models.TextChoices):
    NORMAL = "normal", "정상"
    CAUTION = "caution", "주의"
    PREDICT_WARN = "predict_warn", "예측경고"
    WARNING = "warning", "경고"       # 추가
    DANGER = "danger", "위험"
```

**왜 회귀였나**:
- fastapi `combine_risk_5axis` 출력 도메인이 5단계 (`risk_combine.py:148` 명시 — "normal | caution | predict_warn | warning | danger")
- DRF enum 이 4단계
- fastapi 가 `combined="warning"` 인 행을 forward 하면 DRF Serializer 가 `validation_failed` 400 거부
- 외부 리뷰어 [[alarm_dataflow_review_2026_05_20]] #1 (a/c path 충돌) 의 본체

**연쇄 영향 면적 검토 결과 (조사)**: frontend 알람 표시는 별도 enum `RiskLevel` (3단계) 사용 → 영향 없음. admin 자동 반영. 차트·통계에서 `RiskClassified` 별 4단계 가정 분기 코드 없음. choices 추가는 schema 변경 아님 (CharField max_length=20 충분).

### 2.4 fastapi vocab 동기화 (회귀 #2 후속)

3곳 매핑에 "warning" 추가 — DRF 측 enum 만 추가하면 fastapi 자신은 "warning" 키가 없어 silent fallback "normal" 잠재 회귀 발생.

- [power_service.py:65](../../../../fastapi-server/power/services/power_service.py#L65) `_COMBINED_TO_RISK_LEVEL` 에 `"warning": "warning"` 추가
- [power_service.py:71](../../../../fastapi-server/power/services/power_service.py#L71) `_FIRE_LEVELS` 에 `"warning"` 추가 (없으면 WebSocket fire 흐름 누락)
- [decide_alarm.py:37-50](../../../../fastapi-server/power/services/decide_alarm.py#L37-L50) `_ai_combined_to_risk_level` 에 `"warning": "warning"` + docstring "AI 5단계 → UI 3단계" 갱신

### 2.5 ARIMA 학습 `max_rows` default 3000 → 10000

**Before** ([train_arima_power_model.py:80-85](../../../../drf-server/apps/ml/management/commands/train_arima_power_model.py#L80-L85))
```python
parser.add_argument("--max-rows", default=3000, ...)
```

**After**
```python
parser.add_argument("--max-rows", default=10000, ...)
```

**왜 보강이 필요했나**:
- 5분 주기 더미 데이터 기준 3000행 = 약 10일치인데, **하루 시간대별 부하 패턴이 다름** (주간 0.55 / 저녁 0.30 / 야간 0.15)
- max_rows 3000 으로 학습 시 최근 윈도우가 한 시간대 부근에 치우침 → ARIMA(1,1,1) ConvergenceWarning 발생 → sigma2 ≈ 0 → 95% CI 폭이 0
- 추론 시 actual 값이 거의 항상 ARIMA violation 으로 판정 → predict_warn/warning 폭주
- max_rows 10000 (~35일 — 사실상 전체 학습 데이터) 으로 학습 시 ConvergenceWarning 없음. sigma2 정상 (예: ch9 sigma=540), 95% CI 폭 ≈ 2117

### 2.6 테스트 정리

[test_anomaly_result_create.py:67](../../../../drf-server/apps/ml/tests/test_anomaly_result_create.py#L67) 의 `invalid_risk_classified` 테스트가 `"warning"` 을 invalid 값으로 사용했었으나, 이젠 valid. invalid 의도는 보존하기 위해 `"bogus"` 로 교체.

---

## 3. 검증 결과

### 3.1 4채널 추론 분기 진입

```
[ai] IF loaded sensor_identifier='power:device_63200c3afd12:ch1:watt' version=11
[ai] IF loaded sensor_identifier='power:device_63200c3afd12:ch9:watt' version=9
[ai] IF loaded sensor_identifier='power:device_63200c3afd12:ch14:watt' version=10
[ai] IF loaded sensor_identifier='power:device_63200c3afd12:ch15:watt' version=8
[ai] ARIMA loaded ... ch1 v3 / ch9 v2 / ch14 v2 / ch15 v2 (max_rows=10000 재학습)
```

채널별 활동 (3분 윈도우, cache evict 직후):

| 채널 | 추론 건수 | normal | caution | warning | DRF 400 |
|---|---|---|---|---|---|
| ch1 | 165 | 0 | 158 | 8 | 0 |
| ch9 | 175 | 30 | 113 | 11 | 0 |
| ch14 | 162 | 0 | 157 | 7 | 0 |
| ch15 | 172 | 0 | 130 | — | 0 |

### 3.2 ARIMA ci 폭 정상화

- 재학습 전: ci 폭 0 비율 75% (sigma2 붕괴)
- 재학습 후: ci 폭 0 비율 0% — 모든 forecast 가 [lo, hi] 폭 보유 (평균 1672, ch9 기준)

### 3.3 DRF 400 해소

- enum 추가 + 매핑 보강 후: forward 549건 → **0건**

### 3.4 caution 의 직접 원인 추적 (보고용)

`combined=caution` 빈도가 높은 이유는 IF/ARIMA FP 가 아니라 **`night_abnormal` 시각 휴리스틱 격상**:

- [power_service.py:459-478](../../../../fastapi-server/power/services/power_service.py#L459-L478) — KST 야간(22~05) + `value > rated × 0.30` 이면 `_NIGHT_ESCALATION["normal"]="caution"` 격상
- 4채널 추론 1276건 중 472건(37%) 이 night_abnormal 격상
- 시연이 KST 주간(08~18) 으로 결정됨 → 시연 시각에는 미발동 → 별도 조치 불필요

---

## 4. 신규 MLModel 현황

| id | algorithm | sensor_identifier | version | 비고 |
|---|---|---|---|---|
| 12 | isolation_forest | ch15:watt | v8 | 시연용 신규 |
| 13 | isolation_forest | ch9:watt | v9 | 시연용 신규 |
| 15 | isolation_forest | ch14:watt | v10 | 시연용 신규 |
| 17 | isolation_forest | ch1:watt | v11 | sid='' 옛 IF (id=4) 대체 |
| 20 | arima | ch9:watt | v2 | max_rows=10000 재학습 |
| 21 | arima | ch1:watt | v3 | max_rows=10000 재학습 |
| 22 | arima | ch14:watt | v2 | max_rows=10000 재학습 |
| 23 | arima | ch15:watt | v2 | max_rows=10000 재학습 |

비활성: id=4 (옛 IF sid=''), id=10 (오류 sid `device_1:ch15`), id=8/9/11/14/16 (max_rows=3000 옛 ARIMA).

---

## 5. 후속 작업

- **un-downgrade 정식 적용 (D+30)**: 본 작업은 더미 데이터 기반 PoC. 정식 적용 근거는 실측 데이터 30일 — [[demo_2026_06_14_arima_roadmap]] 별도 의제.
- **현재 데이터 더미 한정**: `PowerData.source` 같은 더미/실측 구분 필드 추가는 별도 plan.
- **vocabulary 통일 후속**: 본 작업은 enum 5단계 확장으로 처리. 정적 vs AI 두 vocab 의 본질적 통합 (예: 정적도 4단계로 통일) 은 외부 리뷰어 #1 의 더 깊은 해결로 [[alarm_dataflow_review_2026_05_20]] 후속 plan.
- **야간 격상 휴리스틱**: 시각·정격 휴리스틱이 시연 시각 외에는 caution 발화 원인. 더미가 시각 인지하도록 보강하거나 휴리스틱 임계 상향은 별도 plan.

---

## Changelog

- 2026-05-21 작성. 4채널 활성화 + 발견된 회귀 2건 + ARIMA max_rows 본질 + 검증 결과.
