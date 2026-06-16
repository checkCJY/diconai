# 전력 AI un-downgrade Phase 2 — 적용 plan (옵션 A · 가스 영역 보호)

> **상태**: 2026-05-18 작성. 원본 [power-ai-un-downgrade-phase2.md](./power-ai-un-downgrade-phase2.md) 가 2026-05-18 초안 이후 PR #57~#62 변경을 반영하지 못해 본 plan 으로 갭 흡수 + **가스 영역(가스 ARIMA 학습/추론 코드) 보호 결정 반영**.
> **시연 후 진입 전제 유지** — D-27 (시연 2026-06-14), D+30 (완료 2026-07-14).

## Context

원본 plan 은 작성 시점 기준 가정으로 W1·W4.a·W5 작업 단위를 잡았는데, 이후 다음 PR 들이 머지됨:

- **PR #57**: AlarmRecord.channel 추가, 이벤트 패널 재설계
- **PR #58**: IF + ARIMA 가스 통합 (train_arima_model.py 신설, gas_service ARIMA 직접 로드)
- **PR #60**: user-scoped ack (EventAcknowledgement 신규), Redis BRPOP 알람 큐
- **PR #59 / #62**: Prometheus multiproc 버그 수정 + P0 메트릭 11종 중앙화 (apps/core/metrics.py)

또한 결정: 사용자(전력 담당자)가 가스 영역을 담당하지 않으므로 **가스 ARIMA 소스 (train_arima_model.py, gas_service.py, 가스 ARIMA pkl 도구)** 는 0 변경 보호. 가스 ARIMA 의 MLModel 통합(원본 plan W6)은 가스 담당자가 추후 별도 task 로 처리.

영향: (a) W1 RenameField 가 `train_anomaly_model.py` 의 가스/전력 공용 한 줄(L261)만 변경 → 동작 회귀 0, (b) 전력 ARIMA 는 가스용 명령 건드리지 않는 신규 명령(`train_arima_power_model.py`)으로 처리, (c) 원본 W6(가스 백포팅) 삭제, (d) 가스 ARIMA 는 현재 격하 격리 패턴(모듈 import 직접 로드) 그대로 유지.

## 0. 흐름 한 장

```
W0  시나리오 + Quality 가드 (2~2.5일)
  └─→ W1  DB 스키마 — model_type→algorithm RenameField + sensor_identifier (1.5일)
        └─→ W2  모델 로더 분기 — _get_or_load 3축 + _get_or_load_arima (1.5일)
              └─→ W2.5  train_arima_power_model.py 신규 (0.5일)
                    └─→ W3  추론 분기 — IF + ARIMA forecast + 3축 combine (2일)
                          ├─→ W4.a 알람 통합 — algorithm_source (1일)
                          │     └─→ W4.b metrics 라벨 — algorithm_source 라벨 (0.5일, 별도)
                          └─→ W5  운영 + 검증 (2일)

총 10.5~11일 (원본 11.5~12일에서 W6 삭제로 단축)
```

## 1. 핵심 결정 (Q1~Q3 결과)

| 결정 | 근거 |
|---|---|
| **Q1** `MLModel.model_type` → `algorithm` 으로 RenameField + ARIMA choice 추가 | `train_anomaly_model.py` 한 줄(L261)만 따라가면 됨 = 가스 IF 동작 회귀 0. 컬럼 단일 깔끔. |
| **Q2** 전력 ARIMA 는 `train_arima_power_model.py` 신규로 처리 | 가스용 `train_arima_model.py` 절대 건드리지 않음. 가스 영역 보호. 코드 중복은 명령 안의 MLModel row 생성 보일러플레이트 정도(허용). |
| **Q3** EventAcknowledgement (user-scoped ack) 는 Phase 2 범위 외 | dedup 은 device_id·channel·rule_level + algorithm_source 만. user 차원은 broadcast 시점에만 작용. |

**가스 영역 보호 명시**:
- ❌ `train_arima_model.py` (가스 ARIMA 학습) — 0 변경
- ❌ `fastapi-server/gas/services/gas_service.py` (가스 ARIMA 모듈 import 직접 로드) — 0 변경
- ❌ 가스 ARIMA pkl 파일들 (arima_co.pkl 등) — 0 변경
- ✅ `train_anomaly_model.py` 의 L261 한 줄 (`model_type=` → `algorithm=`) — rename 자동 반영, 동작 0 영향
- ➡ 가스 ARIMA 의 MLModel 통합은 가스 담당자가 추후 별도 task 로 (인프라 path `_get_or_load_arima` 는 W2 에서 이미 준비됨)

## 2. 재활용 자산 — 신규 작성 피할 것

| 자산 | 위치 | 재활용 방법 |
|---|---|---|
| ChannelState 상태머신 | `fastapi-server/dummies/_state_machine.py` | maybe_trigger 시그니처에 `time_gate` 옵션 인자만 추가 |
| base_load_ratio | `fastapi-server/dummies/power_dummy.py` L100~113 | night_abnormal time_gate 검사에 그대로 활용 |
| SCENARIO_PATTERNS dict | 〃 | night_abnormal / motor_stuck 신규 키 추가, spike 키만 제거 |
| _power_windows + _last_fired_at | `fastapi-server/power/services/power_service.py` L29~52 | ARIMA 분기에서 동일 deque / rate limit 재사용 |
| forward_inference_e2e | `fastapi-server/services/anomaly_alarm.py` L70~146 | payload dict 에 algorithm_source / arima_forecast 키만 추가 |
| _CachedModel + httpx 캐시 로드 | `fastapi-server/ai/router.py` L38~113 | _CachedArimaModel 도 같은 구조로 |
| combine_risk 2축 매트릭스 | `fastapi-server/ai/risk_combine.py` L31~51 | 기존 함수 유지, 3축은 별도 함수 신설 |
| is_ai_mute_active(device_id, channel, rule_level) | `drf-server/apps/alerts/services/alarm_dedupe.py` | 시그니처 + algorithm_source 인자만 (선택, 무관 동작 유지) |
| MLAnomalyResult.sensor_identifier | `drf-server/apps/ml/models/ml_anomaly_result.py` L39 | 이미 존재 → 추론 시 그대로 채움 |
| `_next_version`, `_parse_dt`, `extract_normal_power_series` | `drf-server/apps/ml/management/commands/train_anomaly_model.py` / `apps/ml/services/dataset_service.py` | train_arima_power_model.py 안에서 import 재사용 |
| apps/core/metrics.py 11종 | `drf-server/apps/core/metrics.py` (PR #62) | ALARM_FIRED_TOTAL / RULE_FIRE_SUPPRESSED_BY_AI_TOTAL 에 algorithm_source 라벨만 추가 |
| EventAcknowledgement | `drf-server/apps/alerts/models/event_acknowledgement.py` (PR #60) | 손대지 않음 — broadcast 시점 알람 dedup 용 |
| Redis BRPOP 알람 큐 | `fastapi-server/websocket/services/alarm_queue.py` (PR #60) | 손대지 않음 — alarm push 흐름 그대로 |
| **가스 ARIMA 격하 격리 자산** | `train_arima_model.py`, `gas_service.py` `_arima_models` dict | **손대지 않음** — 가스 담당자 영역 |

## 3. W0 — 시나리오 + Quality 가드 (2~2.5일)

**왜**: ARIMA forecast 가치 시연을 위해 학습 데이터 패턴 정렬 + 통신/센서 오류가 IF 학습에 흡수되는 것 방지. **선행작업**: 없음.

### 3.1 변경
- `fastapi-server/dummies/power_dummy.py`: spike 제거, night_abnormal·motor_stuck 추가, 가중치 P0 70 / P1 15 / 보조 15 재분배. **dummy 측 시각 게이트 없음** — night_abnormal 의 "야간 시각" 판정은 W3 추론 측 책임 (책임 분리). dummy = 데이터 생성, 추론 = 판정.
- `fastapi-server/dummies/_state_machine.py`: **변경 없음**.
- `fastapi-server/core/power_thresholds.py`: UPPER_BOUND_BY_TYPE = {"watt": 50000, "current": 200, "voltage": 600} 상수 추가
- `fastapi-server/power/services/quality_guard.py` **(신규)**: `classify_sensor_status(value, data_type) -> str|None` (None/comm_failure/sensor_fault_overflow) + `is_inference_stuck(history) -> bool` (윈도우 가득 + 모든 값 동일 판정). numpy 미사용.
- `fastapi-server/power/services/power_service.py`: process_anomaly_inference 진입부에 quality_guard 두 검사 추가 (윈도우 적재 전 classify, 윈도우 가득 후 stuck). skip 시 logger.debug 로 사유 라벨 기록.

### 3.2 회귀 가드
- _state_machine 0 변경 + dummy 시각 게이트 없음 → 기존 4종 시나리오 (overload/voltage_drop/phase_loss/degradation) 동작 회귀 0
- POWER_THRESHOLDS 그대로 두고 UPPER_BOUND_BY_TYPE 만 새 상수 (충돌 0)
- quality_guard 는 추론 측 전용 — raw 데이터 저장 흐름 (to_channel_list / DRF) 0 영향, sensor_status raw 라벨링은 현재 None=comm_failure 만 유지

### 3.3 검증 (Makefile 기준)

```bash
# 1) 코드 반영 — fastapi 재시작 (dummy 도 함께 죽음)
make restart s=fastapi

# 2) dummy 재기동
make dummies-restart s=power

# 3) quality_guard 동작 확인 — None 값 강제 주입
curl -X POST http://localhost:8001/api/power/watt \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"63200c3afd12","slave01":null}'

# 4) 로그 확인 (fastapi 추론 측)
make logs s=fastapi | tail -200 | grep "anomaly_inference.*skip"
# 기대: "[anomaly_inference] skip ... status=comm_failure|sensor_fault_overflow|sensor_fault_stuck"
```

검증 포인트:
- value=None / value=-1 → "status=comm_failure" + 윈도우 적재 skip
- value=50000 초과 watt 주입 → "status=sensor_fault_overflow"
- 동일 값 30틱 연속 (윈도우 가득) → "status=sensor_fault_stuck"
- raw 측 power_data.sensor_status 컬럼은 변경 없음 (None=comm_failure 만 라벨 유지)
- W0 동기화 누락 방지: 신규 모드(night_abnormal/motor_stuck)는 `_scenario.py` + `internal/routers/scenario_router.py` 양쪽 ALLOWED_MODES 동시 등록 필수
- night_abnormal 강제 진입 시 dummy 는 즉시 데이터 송신 (시각 무관) — 추론 측 야간 시각 분기는 W3 에서 추가

## 4. W1 — DB 스키마 (1.5일)

**왜**: un-downgrade의 핵심 — ARIMA 를 IF 와 동등 algorithm 으로 분리. **선행작업**: W0 완료.

### 4.1 마이그레이션 (0002)

```python
# drf-server/apps/ml/migrations/0002_rename_model_type_to_algorithm.py
operations = [
    # 1) model_type → algorithm RenameField (데이터 그대로 보존)
    migrations.RenameField(
        model_name="MLModel",
        old_name="model_type",
        new_name="algorithm",
    ),
    # 2) ARIMA choice 추가 + verbose_name 갱신
    migrations.AlterField(
        model_name="MLModel",
        name="algorithm",
        field=models.CharField(
            max_length=30,
            choices=[
                ("isolation_forest", "Isolation Forest"),
                ("arima", "ARIMA"),
            ],
            default="isolation_forest",
            verbose_name="모델 알고리즘",
        ),
    ),
    # 3) sensor_identifier 추가
    migrations.AddField(
        model_name="MLModel",
        name="sensor_identifier",
        field=models.CharField(
            max_length=64,
            blank=True,
            default="",
            verbose_name="센서 식별자",
            help_text=(
                "ARIMA 등 단일 시계열 모델용. 예: 'power:device_1:ch3:watt'. "
                "비어 있으면 sensor_type 단위 (전 sensor 공유)."
            ),
        ),
    ),
    # 4) 제약 변경 — 기존 uq_ml_model_sensor_version 제거 → 4축 조합
    migrations.RemoveConstraint(model_name="MLModel", name="uq_ml_model_sensor_version"),
    migrations.AddConstraint(
        model_name="MLModel",
        constraint=models.UniqueConstraint(
            fields=["sensor_type", "algorithm", "sensor_identifier", "version"],
            name="uq_ml_model_sensor_alg_id_version",
        ),
    ),
    migrations.AddConstraint(
        model_name="MLModel",
        constraint=models.UniqueConstraint(
            fields=["sensor_type", "algorithm", "sensor_identifier"],
            condition=models.Q(is_active=True),
            name="uq_ml_model_active_per_match_unit",
        ),
    ),
]
```

기존 IF row 들은 RenameField 로 자동 보존, algorithm='isolation_forest' / sensor_identifier='' default 적용.

### 4.2 변경 파일
- `drf-server/apps/ml/models/ml_model.py`: `ModelType` 클래스명 → `Algorithm` 으로 rename + `ARIMA = "arima", "ARIMA"` choice 추가. `model_type` 필드명 → `algorithm` 으로. `sensor_identifier` 필드 추가. Meta constraints 갱신. `__str__` 표시 갱신.
- `drf-server/apps/ml/migrations/0002_*.py` 신규 (위 4 operations)
- `drf-server/apps/ml/serializers/`: API 응답에 algorithm / sensor_identifier 포함
- `drf-server/apps/ml/views.py` `ActiveMLModelView.get_object` L49~60: 쿼리 파라미터 `algorithm` (default='isolation_forest') / `sensor_identifier` (default='') 처리. 기존 IF 단일 매칭 회귀 0.
- `drf-server/apps/ml/management/commands/train_anomaly_model.py` L261: `model_type=MLModel.ModelType.ISOLATION_FOREST` → `algorithm=MLModel.Algorithm.ISOLATION_FOREST` **(한 줄 변경, 가스/전력 IF 공통)**. 부가로 L258~269 의 create 호출에서 `sensor_identifier` 도 채움 (power: f"power:device_{}:ch{}:{}", gas: f"gas:sensor_{}:{}").

### 4.3 검증
- 마이그레이션 적용 후 기존 6 row 의 algorithm=='isolation_forest' / sensor_identifier=='' 확인
- 가스 IF 학습 1회 재실행 → 정상 완료 + 새 row 의 sensor_identifier=='gas:sensor_1:co' 같은 형식
- 가스 IF 추론 회귀 — `_get_or_load("gas")` 가 active row 로드되는지 (W2 진입 전 sanity check)
- 가스 ARIMA 모듈 import 시 직접 로드 (gas_service.py L37~44) 정상 동작 확인 — **이 코드는 안 건드림**

## 5. W2 — 모델 로더 분기 (1.5일)

**왜**: W1 컬럼을 받아 다중 모델 캐시·로드. ARIMA 헬퍼는 W2.5 의 전력 ARIMA 학습 결과를 fastapi 가 로드할 수 있게 준비. **선행작업**: W1 완료.

### 5.1 변경
- `fastapi-server/ai/router.py` `_get_or_load(sensor_type, algorithm="isolation_forest", sensor_identifier="")` 시그니처 확장. 캐시 키 `(sensor_type, algorithm, sensor_identifier)`. 기본값 호출(`_get_or_load("gas")`) 회귀 0.
- `fastapi-server/ai/router.py` `_CachedArimaModel` 클래스 신규 (statsmodels ARIMAResultsWrapper 보관)
- `fastapi-server/ai/router.py` `_get_or_load_arima(sensor_identifier)` async helper 신규
- `fastapi-server/ai/router.py` `/ai/reload` 엔드포인트 — `algorithm` / `sensor_identifier` 쿼리 파라미터 추가. algorithm 없으면 sensor_type 전체 evict.
- `drf-server/apps/ml/views.py` `ActiveMLModelView.get_object`: algorithm·sensor_identifier 쿼리 파라미터 매칭. 기본값 그대로면 기존 IF 단일 매칭 회귀 0.

### 5.2 검증
- `curl http://drf:8000/api/ml/models/active/?sensor_type=power` → IF v6 메타 (회귀)
- `curl http://drf:8000/api/ml/models/active/?sensor_type=gas` → 가스 IF active 메타 (회귀)
- `curl 'http://drf:8000/api/ml/models/active/?sensor_type=power&algorithm=arima&sensor_identifier=power:device_1:ch1:watt'` → 404 (아직 학습 안 됨, W2.5 이후 200)

## 6. W2.5 — `train_arima_power_model.py` 신규 (0.5일)

**왜**: 전력 ARIMA 학습 + MLModel row 생성. 가스용 `train_arima_model.py` 0 변경 유지. **선행작업**: W1 (algorithm 컬럼) + W2 (`_get_or_load_arima` reload path) 완료.

### 6.1 변경
- `drf-server/apps/ml/management/commands/train_arima_power_model.py` **(신규)**:
  - add_arguments: `--device-id` / `--channel` / `--data-type` / `--since` / `--until` / `--p` / `--d` / `--q` / `--activate`
  - `extract_normal_power_series` 재사용 (`apps/ml/services/dataset_service.py`)
  - `_next_version` / `_parse_dt` 헬퍼는 `train_anomaly_model.py` 에서 import (모듈 함수 노출 필요 시 _underscore 제거 후 재export, 또는 사본 작성. 명령 1개라 사본 0.5일 안에 충분).
  - statsmodels ARIMA 학습 → joblib.dump (`{sensor_type}_arima_v{version}_{sensor_identifier_safe}.pkl` 같은 규칙. 예: `power_arima_v1_power_device_1_ch1_watt.pkl`)
  - `with transaction.atomic():` 블록에서 `MLModel.objects.create(algorithm="arima", sensor_type="power", sensor_identifier=f"power:device_{}:ch{}:{}", ...)` + `--activate` 시 기존 활성 비활성화

### 6.2 회귀 가드
- 가스용 `train_arima_model.py` 는 절대 건드리지 않음 — 기존 가스 ARIMA pkl 들 (arima_co/h2s/co2.pkl) 그대로 사용 가능.
- 새 명령 파일은 가스 학습 명령과 import 의존성 없음.

### 6.3 검증
- `python manage.py train_arima_power_model --device-id 1 --channel 1 --data-type watt --since 2026-05-12 --until 2026-05-15 --activate`
- → pkl 파일 + MLModel row (algorithm='arima', sensor_identifier='power:device_1:ch1:watt', is_active=True)
- → `curl 'http://drf:8000/api/ml/models/active/?sensor_type=power&algorithm=arima&sensor_identifier=power:device_1:ch1:watt'` → 200

## 7. W3 — 추론 분기 (2일) — 핵심

**왜**: ARIMA forecast 가 IF 와 동급 판단자로 동작. **선행작업**: W2 / W2.5 완료.

### 7.1 변경 (원본 plan §5 와 동일)
- `fastapi-server/ai/router.py` `_arima_forecast(values, arima_result, alpha=0.05) -> dict` 신규 — forecast / ci_lower / ci_upper / actual / is_violation
- `fastapi-server/ai/risk_combine.py` `combine_risk_3axis(threshold_risk, if_prediction, arima_violation) -> str` 신규. 기존 combine_risk 유지.
- `fastapi-server/power/services/power_service.py` `process_anomaly_inference`:
  - sensor_identifier = f"power:device_{}:ch{}:{}"
  - IF 추론 후 `_get_or_load("power", "arima", sensor_identifier)` 추가. 404 시 arima_result=None / arima_violation=False fallback (모델 학습 안 된 채널은 IF 단독 동작).
  - `combine_risk_3axis(threshold_risk, if_prediction, arima_violation)` 호출
  - **night_abnormal 시각 분기 (W0 에서 이관)**: measured_at 의 KST hour 가 22~05 + watt 가 야간 baseline 초과 시 별도 가중치/룰. dummy 가 시각 게이트 없이 항상 night_abnormal 데이터 송신 → 추론 측이 시각 컨텍스트 판정. **현재 W3.2 휴리스틱 (정격 30% 임계치) 으로 충분**. 향후 자동화 옵션 (SARIMAX seasonal / IF hour 피처 / 시각별 동적 임계치) 은 휴리스틱 임계치 수동 튜닝 자동화 — 필수 아님.

### 7.2 회귀 가드
- ARIMA pkl 없는 채널은 fallback 으로 IF 단독 (기존 동작 유지). W2.5 에서 1개 채널만 학습해 두고 시작.
- 가스 측은 본 plan 으로 변경 0 (가스 IF + 가스 ARIMA 격하 그대로).

### 7.3 검증
- 로그에서 `arima_forecast` 출력: forecast / ci / actual / is_violation
- AlarmRecord.algorithm_source / risk_level 확인 (W4.a 완료 후)
- 가스 알람 회귀 — co/h2s/co2 dummy 실행 시 알람 발화 패턴 변화 0

## 8. W4.a — 알람 통합 (1일, 원본 1.5일에서 단축)

**왜**: ARIMA 발화 추적 + dedup 정책 algorithm 무관 처리. **단축 사유**: AlarmRecord.channel 이 PR #57 에서 이미 추가됨 → 필드 1개만 추가하면 됨. AI_TO_RULE_LEVEL 중복도 알려진 surgical cleanup. **선행작업**: W3 완료.

### 8.1 변경
- `drf-server/apps/alerts/models/alarm_record.py`: `algorithm_source` CharField(max_length=30, blank=True, default="") 추가
- `drf-server/apps/alerts/models/event.py`: 동일 필드 추가 여부 — Event 가 AlarmRecord 와 1:N 이면 AlarmRecord 만으로 충분할 수 있음. 마이그레이션 작성 전 alerts/event_service.py 의 Event 생성 코드 확인 후 결정.
- `drf-server/apps/alerts/migrations/0017_*.py` 신규 (현재 0016 까지 — 진입 시점에 최신 번호 재확인)
- `drf-server/apps/alerts/services/alarm_dedupe.py` `is_ai_mute_active`: algorithm_source 인자 optional 추가 (현재 시그니처 그대로 두면 무관 동작 유지 — 양쪽 piggyback)
- `drf-server/apps/core/constants.py` L75, L88: 중복된 AI_TO_RULE_LEVEL 정리 (한 쪽 제거)
- `fastapi-server/power/services/power_service.py`: forward_inference_e2e payload 에 algorithm_source / arima_forecast 키 추가
- `fastapi-server/services/anomaly_alarm.py`: alarm_payload / push_payload pass-through (현재 dict 형태로 유연 → 키 추가만)
- `drf-server/apps/core/metrics.py` ALARM_FIRED_TOTAL / RULE_FIRE_SUPPRESSED_BY_AI_TOTAL 에 algorithm_source 라벨 추가 (메트릭 정합성)

### 8.2 검증
- IF 단독 → algorithm_source='isolation_forest'
- ARIMA 단독 → 'arima'
- 동시 발화 → 'combined'
- mute 60s 동안 룰 알람 suppress (algorithm 무관)
- Prometheus `alarm_fired_total{algorithm_source="arima"}` 카운트 증가
- 가스 알람의 algorithm_source 는 빈 문자열(가스 코드 변경 없음) — 메트릭/UI 에 빈 라벨 처리 확인

## 9. W5 — 운영 + 검증 (2일)

**왜**: 모델 수 증가 → 결과 폭주 방지 + 주기 재학습 + 6종 시나리오 end-to-end. **선행작업**: W4.a 완료.

### 9.1 위치 보정 (원본 plan 과 차이)
- DataRetentionPolicy 등록: `drf-server/apps/operations/models/data_retention_policy.py` (원본 plan 의 `apps/core/data_retention.py` 가정 stale)
- Celery beat 등록: `drf-server/config/settings.py` `CELERY_BEAT_SCHEDULE` dict (원본 plan 의 `config/celery.py` 가정 stale)

### 9.2 변경
- `apps/operations/` 에 MLAnomalyResult TTL 정책 row 추가 (retention_days=7, batch_size=1000). 기존 `apps.operations.tasks.data_retention_task.run_data_retention` 가 자동 처리.
- `drf-server/apps/ml/tasks/retrain.py` 신규: `retrain_active_arima()` shared_task — `MLModel.objects.filter(algorithm="arima", is_active=True)` 순회 → `train_arima_power_model` command 재실행 → 새 row 생성 + 기존 비활성화. **가스 ARIMA 는 MLModel row 가 없으므로 자동으로 대상에서 제외됨** (격리 자연 효과).
- `config/settings.py` CELERY_BEAT_SCHEDULE 에 `retrain-arima-weekly` 등록 (crontab(day_of_week=0, hour=2))

### 9.3 통합 검증
- 6종 시나리오 (overload / degradation / night_abnormal / motor_stuck / voltage_drop / phase_loss) 각 강제 진입 → alarm_record.algorithm_source 분포 확인
- Grafana 대시보드 `alarm_fired_total` / `rule_fire_suppressed_by_ai_total` 패널에서 algorithm_source 분리 확인
- 가스 dummy 1회 실행 → 가스 측 알람 발화 패턴 회귀 0 (가스 코드 0 변경 검증)

## 10. 일정 + 리스크

```
시연 2026-06-14 (D-27)
  +1주 (~07-01): W0 시나리오 + Quality 가드
  +2주 (~07-08): W1·W2·W2.5 DB + 로더 + 전력 ARIMA 학습 명령
  +3주 (~07-15): W3·W4.a 추론 + 알람
  +4주 (~07-22): W5 운영 (W6 삭제로 1주 여유)
D+30 (~07-14): un-downgrade 완료 (일정 여유 8~10일)
```

| 리스크 | 완화 |
|---|---|
| RenameField 가 운영 SQLite 에서 ALTER COLUMN 한계 | 마이그레이션 dry-run + 백업 후 적용. 실패 시 add+copy+drop 대안. |
| `train_anomaly_model.py` 한 줄 변경이 가스 동작에 영향 | rename + enum 참조 한 줄 = 컬럼명만 바꿈, 가스 IF 학습/추론 동작 0 영향. W1 검증 단계에 가스 IF 1회 재학습 + 추론 회귀 포함. |
| AlarmRecord 0017 마이그레이션이 PR #57 의 0016 과 충돌 | 본 plan 진입 시점에 latest migration 재확인 → 다음 번호 산정 |
| metrics.py 라벨 추가로 기존 Grafana 패널 깨짐 | 라벨 추가 시 기존 합계 패널은 `sum without (algorithm_source)` 표현으로 보정 |
| EventAcknowledgement 도입으로 broadcast 흐름 변화 | Q3 결정 — Phase 2 범위 외. dedup 영향 없음. |
| ARIMA forecast latency (inline apply()) | Phase 3 background 분리 검토 — 현재는 측정 우선 |
| 가스 ARIMA 격하 격리 유지로 가스측 인프라 일관성 결여 | 가스 담당자가 추후 별도 task 로 처리. 본 plan 의 `_get_or_load_arima` path 가 준비되어 있어 가스 측은 호출만 바꾸면 됨. |

## 11. 산출물 체크리스트

W0 ✅ (2026-05-18 코드 완료, lint 통과 / docker 실행 검증은 사용자 진행)
- [x] power_dummy spike 제거, night_abnormal·motor_stuck 추가, 가중치 재분배 (30/8/7/20/20/15)
- [x] dummy 시각 게이트 없음 (책임 분리) — night_abnormal 시각 판정은 W3 추론 측으로 이관
- [x] core/power_thresholds UPPER_BOUND_BY_TYPE 상수
- [x] power/services/quality_guard.py 신규 (classify_sensor_status + is_inference_stuck) + power_service.process_anomaly_inference 호출
- [x] dummy mode validator 양쪽 (_scenario.py + scenario_router.py) ALLOWED_MODES 동기화 + 헤더 docstring 갱신
- [x] quality_guard skip 로그 logger.info 로 설정 (LOG_LEVEL=INFO 환경 가시성)
- [x] docker compose 환경에서 quality_guard 실제 동작 검증 (2026-05-18 — `slave01=-1`/`slave01=60000` 주입 → `[anomaly_inference] skip status=comm_failure|sensor_fault_overflow` 확인)

W1 ✅ (2026-05-18 commit 65dc9f1 + af05e78)
- [x] MLModel model_type→algorithm RenameField + ARIMA choice (W1.1)
- [x] sensor_identifier 필드 + 제약 변경 마이그레이션 0002 (W1.1)
- [x] 기존 7 row default 처리 확인 — 모두 algorithm='isolation_forest', sensor_identifier='' (W1.1)
- [x] views serializer algorithm 노출 + ActiveMLModelView 쿼리 파라미터 (algorithm/sensor_identifier) 확장 (W1.2)
- [x] train_anomaly_model.py 필드명 + sensor_identifier 자동 생성 (W1.2)
- [x] 전력 IF 추론 회귀 0 검증 (2026-05-18 — fastapi 재시작 + dummy 재시작 후 ch1 watt `pred=normal combined=normal score=0.27~0.29` 정상)
- [ ] 가스 IF 추론 회귀 (W2 완료 후 gas dummy 재시작 시 함께 확인)

W2 ✅ (2026-05-18 — fastapi/ai/router.py)
- [x] _get_or_load 3축 시그니처 — default 호출 _get_or_load("power") 회귀 0
- [x] _CachedArimaModel + _load_arima_pkl + _get_or_load_arima
- [x] /ai/reload 쿼리 파라미터 확장 (algorithm 미지정 시 sensor_type 전체 evict)
- [x] ActiveMLModelView 쿼리 파라미터 (W1.2 에서 이미 완료)
- [x] 재시작 + dummy 회귀 검증 OK ([ai] IF loaded sensor_identifier='' version=3)

W2.5 ✅ (2026-05-18 — commit f69b893 + 실학습 검증)
- [x] train_arima_power_model.py 신규 (전력 전용, --activate 옵션)
- [x] MLModel row 생성 (id=8, sensor_identifier=power:device_1:ch1:watt, active)
- [x] pkl 파일명 규칙 (`power_arima_v{version}_{sid_safe}.pkl`)
- [x] 실학습 검증 — 24547 rows → ARIMA(1,1,1) 3000 rows, pkl 8.5MB
- [x] fastapi `_get_or_load_arima` 로드 검증 — ARIMAResultsWrapper version=1 order=(1,1,1)
- [x] drf/fastapi 이미지 재빌드 (statsmodels==0.14.2 설치, requirements 누락 정비)

W3 ✅ (2026-05-18 commit e1ec403 + W3.2 commit)
- [x] _arima_forecast helper (실모델 forecast=1091.57 CI=[645,1538] 통과)
- [x] combine_risk_3axis 매트릭스 (12 조합 sanity 통과)
- [x] process_anomaly_inference ARIMA 분기 + 404 fallback
- [x] night_abnormal 추론 측 시각 분기 (rated_w × 0.30 임계치 + KST 22~05) — IF + ARIMA + 정적 룰 + 시각 휴리스틱 4축 결합으로 시연 충분. 자동화 옵션 (SARIMAX / IF 다피처 / 동적 임계치) 은 미래 정교화 영역
- [x] 8000W 주입 검증: combined=danger (3축 정확), _is_night_kst_iso 6 sanity 통과
- [ ] 가스 알람 회귀 0 (사용자 진행 — gas dummy 띄우고 [AI 이상탐지] 로그 확인)

W4.a ✅ (2026-05-18 commit 2205a13 + Critical #1 보강 e66450f. 검증 통과 + celery 재시작 필수 메모)

> **주의 (잠재 리스크)**: Django SQLite 의 ALTER TABLE ADD COLUMN 이 column DEFAULT 를 SQL 측에 적용 안 함 (`notnull=1 default=None`). ORM 측 `default=""` 만 의존. 마이그레이션 0017 적용 후 **celery 컨테이너 재시작 필수** — 옛 ORM 메타가 INSERT 시 algorithm_source 누락하면 IntegrityError. raw SQL INSERT 도 위험. 영구 해결은 별도 0018 마이그레이션 (TABLE RECREATE + DEFAULT 적용) 또는 algorithm_source null=True. 현재는 ORM 만 사용해 안전.

- [x] AlarmRecord.algorithm_source 필드 (Event 미적용 — AlarmRecord 만으로 충분)
- [x] alerts 마이그레이션 0017_alarmrecord_algorithm_source (22830 row 빈값 default)
- [x] AI_TO_RULE_LEVEL 중복 dict 단일화 (constants.py)
- [x] forward_inference_e2e payload 확장 + event_service / serializer / view 동행
- [x] fastapi power_service algorithm_source 우선순위 결정 (night_abnormal > combined > arima > isolation_forest)
- [x] 8000W 주입 검증 — AlarmRecord algorithm_source='isolation_forest' 저장 확인
- [ ] is_ai_mute_active algorithm_source optional 인자 — 시그니처 그대로 유지 (plan §8 권장 선택, mute 키 algorithm 무관 piggyback 의도)
- [ ] **W4.b metrics 라벨 추가** — ALARM_FIRED_TOTAL/RULE_FIRE_SUPPRESSED_BY_AI_TOTAL 에 algorithm_source 라벨 + caller 7곳 변경 + Grafana 패널 보정 (별도 commit, W5 이전 또는 이후 결정)

W5
- [ ] apps/operations DataRetentionPolicy 에 MLAnomalyResult 등록
- [ ] apps/ml/tasks/retrain.py + config/settings.py CELERY_BEAT_SCHEDULE
- [ ] 6종 시나리오 end-to-end 검증
- [ ] 가스 측 알람 발화 패턴 회귀 0 검증

## 12. 가스 영역 추후 task (Phase 2 범위 외)

가스 담당자가 별도로 진행할 항목 — 본 plan 의 인프라가 이미 준비되어 있어 코드 변경 최소:
1. **`train_arima_model.py`**: MLModel row 생성 코드 추가 (algorithm='arima', sensor_identifier=f"gas:sensor_{id}:{gas_name}"). pkl 파일은 그대로.
2. **`gas_service.py`**: 모듈 import 시 직접 로드(L37~44) 제거 → `_get_or_load_arima(sensor_identifier)` 경유 (W2 헬퍼 활용). 404 시 격하 피처 제외 fallback.
3. **`gas_service.py`** 진입부 None / -1 가드 추가 (W0 quality_guard 와 동일 패턴 적용).

이 3개가 가스 ARIMA 의 격하 격리 해제 task. Phase 2 완료 후 가스 담당자와 협의 시 본 plan §12 참조.
