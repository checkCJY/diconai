# 가스 Phase 3 — 라벨 인프라 + ml 앱 가스 분기 활성화

> **이 문서를 처음 보는 팀원께**: 본 PR 로 **가스 도메인이 ml 앱(IF 이상탐지)을 사용할 수 있게** 됐습니다. 전력 트랙이 먼저 Phase 3([`../power_phase1_2/power_phase3.md`](../power_phase1_2/power_phase3.md)) + ML STEP 1([`ml_step1_infra.md`](ml_step1_infra.md))을 완료한 후, 가스도 같은 패턴을 그대로 복제하면서 ml 앱의 generic 인터페이스(`sensor_type=power|gas`)에 가스 분기를 활성화했습니다.

**브랜치**: `feature/power_refactory` · **커밋 단위**: 8개 (G1~G8) · **상세 plan**: [skill/plan/if-integration-guide.md](../../../skill/plan/if-integration-guide.md) · **참조 패턴**: 전력 Phase 3 changelog([`../power_phase1_2/power_phase3.md`](../power_phase1_2/power_phase3.md))

---

## 한눈에 보기 — 이 PR 후 가능해진 것

```bash
# (1) 가스 학습 — 전력과 같은 커맨드 인터페이스, sensor-type 만 다름
python manage.py train_anomaly_model \
    --sensor-type gas --sensor-id 1 --gas-name co \
    --since 2026-05-12 --until 2026-05-14 \
    --contamination 0.01 --activate

# (2) 가스 추론 — fastapi 가 active 모델 자동 로드 후 응답
curl -X POST http://localhost:8001/ai/predict \
  -H 'Content-Type: application/json' \
  -d '{"sensor_type":"gas","sensor_identifier":"gas:sensor_1:co","window_values":[...]}'

# (3) 가스 단일 시나리오 격리 테스트 (전력 overload 같은 패턴)
curl -X POST http://localhost:8001/internal/scenario/mode \
  -H 'Content-Type: application/json' -d '{"mode":"co_leak"}'
```

---

## 왜 이 작업이 필요했나 (배경 설명)

### Before — 가스 트랙이 ml 앱을 못 쓰던 이유

| 항목 | 이전 상태 | 무엇이 문제였나 |
|---|---|---|
| GasData 모델 | 가스값 + 위험도만 저장 | "이 row 가 정상이었나 사고였나" 라벨이 없음 — IF 학습 시 정상/이상 구분 불가 |
| gas_dummy v2 | 시나리오 4종 진입 결정만 함 | DB 에는 시나리오 사실이 안 남음 — 학습 후 평가 불가 |
| FastAPI 페이로드 | gas 측정값만 | 시뮬레이터가 라벨을 보낼 통로 없음 |
| ml 앱 dataset_service | 전력 함수만 | 가스 데이터 추출 불가 |
| ml 앱 train 커맨드 | `sensor-type=gas` 호출 시 `NotImplementedError` | 가스 학습 차단 |

### After — 본 PR 적용 후

| 항목 | 변경 후 |
|---|---|
| GasData | `is_anomaly`(bool) + `anomaly_type`(4종 choices) 추가 — 전력과 1:1 동일 패턴 |
| gas_dummy v3 | 상태머신(RAMP/HOLD/DOWN) + 가중치 + 라벨 페이로드 동봉 → IF 가 시계열 자기상관 학습 가능 |
| FastAPI 페이로드 | `anomaly_type: str | None` 옵션 필드 — 운영 센서는 None 유지 (호환) |
| ml 앱 | `extract_normal/labeled_gas_series()` 함수 추가 + train 커맨드 `sensor-type=gas` 분기 활성화 |

---

## 전력 Phase 3 와 다른 점 (가스 도메인 본질 차이)

같은 IF 학습 인프라이지만 데이터 구조 자체가 달라서 몇 가지 결정이 다릅니다.

| 항목 | 전력 | 가스 |
|---|---|---|
| 저장 구조 | long-format — `(device, channel, data_type)` 별 row | **wide-format** — 한 row 에 9 가스 동시 저장 |
| 라벨 단위 | 채널별 (예: ch1=overload, ch2=정상) | **row 단위** (1개 사고가 9가스 모두 영향) |
| 페이로드 라벨 필드 | `anomaly_labels: dict[str, str]` (채널별 매핑) | **`anomaly_type: str`** (단일 시나리오) |
| 상태머신 | 16채널 각자 독립 `ChannelState` | **9가스가 `ChannelState` 1개 공유** |
| 시나리오 가중치 | `[6, 4, 2, 2, 1]` (overload dominant) | **`[6, 4, 4, 4]`** (편향 없음) |
| AnomalyType | overload/voltage_drop/spike/phase_loss/degradation | **co_leak/h2s_leak/fire/chemical_spill** |
| dataset_service 시그니처 | `extract_*_power_series(device_id, channel, data_type, ...)` | **`extract_*_gas_series(sensor_id, gas_name, ...)`** |

**왜 row 단위 라벨인가**: 가스 사고 유형(co_leak/fire 등)은 본질적으로 "1개 사건이 여러 가스에 동시 영향" — co_leak 일 때 co↑ + co2↑ + o2↓ 가 같이 발생. JSON 컬럼으로 가스별 별도 라벨 저장도 고려했지만(옵션 C), 실제로 가스별로 다른 시나리오가 동시 발생하는 케이스가 없어서 over-engineering. 전력 패턴 그대로 복제(옵션 D)가 simplest.

---

## 단계별 변경 (G1 ~ G8)

각 단위가 독립 커밋으로 분리되어 있어 PR 리뷰 시 단위별로 확인 가능합니다.

### G1 — GasData 라벨 필드 추가 ([커밋 `7738645`](.))

**무엇**
- `GasData.AnomalyType` enum 4종 (co_leak/h2s_leak/fire/chemical_spill)
- `is_anomaly` (BooleanField) + `anomaly_type` (CharField, nullable)
- 인덱스 `idx_gas_anomaly_time` (`is_anomaly`, `-measured_at`) — 학습 데이터 추출 가속
- 마이그레이션 `0007_gasdata_is_anomaly_anomaly_type`

**왜**
- IF 가 정상 데이터로만 학습되려면 `WHERE is_anomaly=False` 필터링이 필수
- 평가 단계에선 시나리오별 detection rate 측정용 라벨 필요

**파일**: [`drf-server/apps/monitoring/models/gas_data.py`](../../../drf-server/apps/monitoring/models/gas_data.py)

### G2 — Serializer 라벨 통과 ([커밋 `7bc5200`](.))

**무엇**
- `GasDataCreateSerializer.Meta.fields` 에 두 필드 추가 — ModelSerializer 가 자동으로 GasData 인스턴스에 매핑
- 시리얼라이저 docstring 보강 (운영/시뮬레이터 사용 구분 명시)

**왜**
- G1 의 모델 필드가 있어도 시리얼라이저가 받지 않으면 FastAPI 페이로드의 라벨이 DB 까지 도달 못함

**파일**: [`drf-server/apps/monitoring/serializers/gas_data.py`](../../../drf-server/apps/monitoring/serializers/gas_data.py)

### G3 — FastAPI 페이로드 anomaly_type 필드 ([커밋 `9562fbb`](.))

**무엇**
- `GasDataPayload.anomaly_type: str | None = None` 옵션 필드 추가

**왜**
- pydantic 의 기본 `extra=ignore` 라 schema 에 없으면 시뮬레이터가 보낸 라벨이 버려짐
- 운영 센서는 anomaly_type 을 안 보냄 → None 으로 매핑되어 자동 호환

**파일**: [`fastapi-server/gas/schemas/gas.py`](../../../fastapi-server/gas/schemas/gas.py)

### G4 — gas_service 가 DRF 페이로드에 라벨 전달 ([커밋 `53ece14`](.))

**무엇**
- `gas_service.py` 의 `drf_payload` 딕셔너리에 두 줄 추가:
  ```python
  "is_anomaly": payload.anomaly_type is not None,
  "anomaly_type": payload.anomaly_type,
  ```

**왜**
- G3 에서 schema 가 필드를 받아도, drf_payload 에 명시 안 하면 DRF 로 가는 HTTP 요청에 안 실림

**파일**: [`fastapi-server/gas/services/gas_service.py`](../../../fastapi-server/gas/services/gas_service.py)

### G5 — gas_dummy v3 재작성 ([커밋 `2c9d7b3`](.))

**무엇**
- 전력 dummy v3 와 동일한 상태머신 패턴 도입 (`_state_machine.py` 재사용)
- `SCENARIO_PATTERNS` 4종 (ramp_up/hold/ramp_down 파라미터)
- `SCENARIO_WEIGHTS = [6, 4, 4, 4]` — `random.choices` 가중치
- `_gas_state` — 9가스가 ChannelState 1개 공유 (전력과 다른 점)
- `_apply_mode(mode)` / `_build_gas_values(mode)` 신규 함수
- generate_gas_data() 페이로드에 `anomaly_type` 동봉

**왜**
- v2 의 두 가지 한계 해결: (1) 시계열 자기상관 없음 — RAMP/HOLD/RAMP_DOWN 로 점진 전이 (2) DB 라벨 부재 — 페이로드 동봉
- `_state_machine.py` 가 도메인 비종속이라 전력에서 만든 모듈을 그대로 재사용 — 코드 중복 zero

**파일**: [`fastapi-server/dummies/gas_dummy.py`](../../../fastapi-server/dummies/gas_dummy.py)

### G6 — 시나리오 모드 화이트리스트 확장 ([커밋 `60805c4`](.))

**무엇**
- `_scenario.py` + `scenario_router.py` 의 `ALLOWED_MODES` 에 co_leak/h2s_leak/fire/chemical_spill 4종 추가
- `/internal/scenario/mode` OpenAPI description 도 전력 5종 + 가스 4종 모두 명시

**왜**
- G5 의 dummy 가 단일 시나리오 모드를 받을 준비를 했지만, scenario 화이트리스트가 그걸 막으면 422 거부
- 두 파일 모두 동기화 필수 (이전에 전력 검증 시에도 같은 버그 경험)

**파일**: [`fastapi-server/dummies/_scenario.py`](../../../fastapi-server/dummies/_scenario.py), [`fastapi-server/internal/routers/scenario_router.py`](../../../fastapi-server/internal/routers/scenario_router.py)

### G7 — ml/dataset_service 에 가스 함수 추가 ([커밋 `bcd3286`](.))

**무엇**
- `extract_normal_gas_series(sensor_id, gas_name, since, until)` — 정상 데이터 (IF 학습용)
- `extract_labeled_gas_series(sensor_id, gas_name, since, until)` — 라벨 데이터 (평가용)
- `_gas_to_arrays(qs, gas_name)` 헬퍼 — wide-format 컬럼 동적 선택
- `_GAS_NAMES` 화이트리스트 — 잘못된 가스명 차단

**왜**
- 가스 wide-format 에서 시계열을 추출하려면 가스명 컬럼을 지정해 `.values_list` 해야 함 (전력의 long-format `.values_list("value")` 와 시그니처 다름)
- sensor_identifier 패턴 `gas:sensor_{id}:{gas_name}` — 전력의 `power:device_X:chN:type` 과 1:1 대응

**파일**: [`drf-server/apps/ml/services/dataset_service.py`](../../../drf-server/apps/ml/services/dataset_service.py)

### G8 — train_anomaly_model 가스 분기 활성화 ([커밋 `99e3d1e`](.))

**무엇**
- `_fetch_series` 에서 `sensor_type=gas` 분기 활성화 (이전엔 `NotImplementedError`)
- argparse 인자 2개 추가: `--sensor-id`, `--gas-name`
- `params_json` 에 가스 학습 시 sensor_id/gas_name 기록 (재현·추적)
- 모듈 docstring 에 가스 사용 예시 명시

**왜**
- ml 앱 generic 인터페이스의 완성 — `--sensor-type power|gas` 한 옵션만 바꾸면 동일 커맨드로 두 도메인 학습 가능

**파일**: [`drf-server/apps/ml/management/commands/train_anomaly_model.py`](../../../drf-server/apps/ml/management/commands/train_anomaly_model.py)

---

## 검증 결과 (G9 — end-to-end)

### dummy → DB 라벨 적재

```bash
# mixed 모드 (또는 단일 시나리오) 로 가스 dummy 가동
curl -X POST http://localhost:8001/internal/scenario/mode -H 'Content-Type: application/json' -d '{"mode":"mixed"}'
docker exec -d diconai-fastapi-1 python -m dummies.gas_dummy
```

**결과**: 8528 rows 적재, 정상 8488 / 라벨 40 (h2s_leak 27 + chemical_spill 13)

### 가스 학습 1회

```bash
python manage.py train_anomaly_model \
    --sensor-type gas --sensor-id 1 --gas-name co \
    --since 2026-05-06 --until 2026-05-14 \
    --contamination 0.01 --activate
```

**결과**:
- `MLModel.id=2`, `file_path=gas_if_v1.pkl`, training_sample_count=8488
- feature shape (8459, 4) = [`value`, `roll_mean_30`, `roll_std_30`, `diff`]
- **in-sample anomaly 1.00%** (contamination 1.0% 설정과 정확히 일치)
- score range [-0.0321, 0.2710]

### 가스 추론

```bash
# 모델 reload 후 추론
curl -X POST "http://localhost:8001/ai/reload?sensor_type=gas"
curl -X POST http://localhost:8001/ai/predict -H 'Content-Type: application/json' -d '{
    "sensor_type":"gas",
    "sensor_identifier":"gas:sensor_1:co",
    "window_values":[10,12,11,13,9,10,14,11,12,10,11,13,10,12,14,11,9,10,12,13,11,14,10,12,11,10,13,12,11,10]
}'
# → {"anomaly_score":0.2172, "prediction":"normal", "model_version":1, ...}  ✓
```

### 운영 페이로드 호환

```python
# anomaly_type 미포함 페이로드 (운영 센서)
p = GasDataPayload(timestamp=..., device_id=..., o2=20.9, co=10, ...)
print(p.anomaly_type)  # None
# DB 저장: is_anomaly=False, anomaly_type=None  → 운영 데이터 호환 ✓
```

---

## 알려진 제약 / 다음 단계

### 도메인 본질 제약 (가스 인원이 알아야 할 사항)

| # | 항목 | 본 PR 처리 | 후속 |
|---|---|---|---|
| 1 | 학습 데이터 충분량 | 8488 정상 (window\*10=300 임계 통과) | 본격 학습은 24시간+ 데이터 축적 후 v2 학습 권장 |
| 2 | 추론 정확도 | 단일 spike CO 200ppm 미감지 (학습 분포 좁음) | 데이터 축적 + window 조정 + contamination 튜닝 (STEP 3) |
| 3 | 가스 9종 중 1종만 학습 | co 모델 1개 | 가스별 9개 모델 또는 멀티변수 IF (별도 PR) |
| 4 | `DUMMY_RISK_PROBABILITY=0.1` 환경변수 | 시나리오 진입 비율이 높음 (mixed 30틱 중 29건 anomaly) | 운영자가 `.env.docker` 조정 — 코드 변경 불필요. **가스/전력 공유 변수라 가스(상태머신 1개)는 전력(16채널)보다 16배 희소** |
| 5 | 알람 연동 | 추론만 — 알람 발화 없음 | **STEP D (가스 §4-2 또는 통합) — 결합 매트릭스 4단계 분류** |
| 6 | scenario_router 인증 | 내부망 가정 | 운영 진입 시 `INTERNAL_SERVICE_TOKEN` 권장 |

### 독립 코드 리뷰에서 식별된 추가 제약

| # | 항목 | 영향 | 권장 대응 |
|---|---|---|---|
| 7 | **`lel` 가스가 GasData 모델 컬럼 부재** — `raw_payload` JSONField 에만 보관 | `fire` 시나리오의 핵심 신호(lel↑) 시계열을 학습 입력으로 못 씀. co/co2/o2/voc 동반 영향으로 우회 학습. `extract_*_gas_series(gas_name="lel")` 호출 시 `_GAS_NAMES` ValueError | 운영 진입 시 GasData 에 lel 컬럼 추가 + 마이그 (별도 PR) |
| 8 | **`_gas_state` 단일 인스턴스** — 9가스가 한 상태머신 공유 | 시연 중 `co_leak` → `fire` 모드 전환 시 진행 중 시나리오 완료(최대 40초) 후 다음 진입. 전력(16채널)은 일부 채널 NORMAL 가능성 높지만 가스는 stuck 가능성 ↑ | changelog 명시 + 시연 시 모드 변경 전 `co_leak` 종료 대기. 강제 리셋 옵션은 별도 PR |
| 9 | **`extract_normal_gas_series` 가 운영/시뮬 정상 row 미구분** | 학습 데이터에 운영 노이즈 + 시뮬레이터 정상이 섞이면 분포 편향 가능 | 학습 기간 = 시뮬레이터만 동작 가정. 운영 진입 시 `data_source` 출처 필드 도입 검토 |
| 10 | **운영 센서 통신 불능 sentinel 미정의** | 가스는 `value=-1` 같은 sentinel 가드 없음 (전력은 `.exclude(value=-1)`). dummy 는 양수만 보냄 | 운영 진입 시 에어위드 spec 확인 후 가드 추가 |
| 11 | **학습 후 fastapi 캐시 자동 reload 없음** | 가스 학습 완료 후 운영자가 수동 `curl -X POST /ai/reload?sensor_type=gas` 필요. TTL(1시간) 만료까지 대기 | train_anomaly_model 마지막에 reload 호출 또는 stdout 안내 추가 (별도 PR) |
| 12 | **`_state_machine.py` 가 전력/가스 공유** | 한 도메인이 FSM 시그니처 변경 시 다른 도메인 영향 가능 | 현재 도메인 비종속 설계라 안전. 추후 도메인별 분기 필요 시 별도 모듈 분리 |

---

## ml 앱 = 전력 + 가스 둘 다 사용 가능 (사용자 요구사항 충족)

본 PR 완료 후 ml 앱의 generic 인터페이스가 두 도메인 모두 작동:

| 기능 | 전력 (이미 동작) | 가스 (본 PR 로 활성화) |
|---|---|---|
| 라벨 데이터 적재 | `PowerData.is_anomaly/anomaly_type` (Phase 3) | `GasData.is_anomaly/anomaly_type` (G1) ✓ |
| 학습 커맨드 | `--sensor-type power ...` | `--sensor-type gas ...` ✓ |
| MLModel 관리 | sensor_type='power', is_active 1개 | sensor_type='gas', is_active 1개 ✓ |
| FastAPI 추론 | `{sensor_type: "power", ...}` | `{sensor_type: "gas", ...}` ✓ |
| 모델 캐시 | sensor_type 별 독립 | 전력/가스 모델 동시 캐시 ✓ |

---

## 변경 파일 요약 (G1~G8)

| 영역 | 파일 | 변경 | 라인 |
|---|---|---|---|
| G1 모델 | `monitoring/models/gas_data.py` | AnomalyType enum + 2 필드 + 인덱스 | +33 |
| G1 마이그 | `monitoring/migrations/0007_gasdata_is_anomaly_anomaly_type.py` | 신규 | +43 |
| G2 시리얼라이저 | `monitoring/serializers/gas_data.py` | fields 2개 + docstring | +35 / -4 |
| G3 스키마 | `fastapi-server/gas/schemas/gas.py` | anomaly_type 필드 | +5 |
| G4 서비스 | `fastapi-server/gas/services/gas_service.py` | drf_payload 2 라인 | +4 |
| G5 dummy | `fastapi-server/dummies/gas_dummy.py` | v3 재작성 | +133 / -39 |
| G6 모드 | `fastapi-server/dummies/_scenario.py` + `internal/routers/scenario_router.py` | 4종 추가 + description | +30 / -13 |
| G7 ml dataset | `drf-server/apps/ml/services/dataset_service.py` | 가스 함수 2개 + 헬퍼 + docstring | +92 / -9 |
| G8 ml command | `drf-server/apps/ml/management/commands/train_anomaly_model.py` | 가스 분기 + 인자 2개 | +27 / -7 |

**총**: 9 files, ~+400 insertions

---

## 운영자/팀원이 시작할 때 (체크리스트)

이미 적용된 환경에서 가스 ML 을 사용해보려면:

1. `git pull` 후 마이그 적용
   ```bash
   docker exec diconai-drf-1 python manage.py migrate monitoring
   ```

2. fastapi 재기동 (스키마/라우터 변경 반영)
   ```bash
   docker compose restart fastapi
   ```

3. 가스 dummy v3 가동 (mixed 또는 단일 시나리오)
   ```bash
   curl -X POST http://localhost:8001/internal/scenario/mode \
        -H 'Content-Type: application/json' -d '{"mode":"mixed"}'
   docker exec -d diconai-fastapi-1 python -m dummies.gas_dummy
   ```

4. 데이터 축적 확인 (정상 ≥ window×10 = 300건 이상이면 학습 가능)
   ```bash
   docker exec diconai-drf-1 python manage.py shell -c "
   from apps.monitoring.models import GasData
   print('정상:', GasData.objects.filter(is_anomaly=False, co__isnull=False).count())
   print('라벨:', GasData.objects.filter(is_anomaly=True).count())
   "
   ```

5. 학습 실행
   ```bash
   docker exec diconai-drf-1 python manage.py train_anomaly_model \
       --sensor-type gas --sensor-id 1 --gas-name co \
       --since 2026-05-12 --until 2026-05-14 \
       --contamination 0.01 --activate
   ```

6. 추론 호출
   ```bash
   curl -X POST http://localhost:8001/ai/predict \
       -H 'Content-Type: application/json' \
       -d '{"sensor_type":"gas","sensor_identifier":"gas:sensor_1:co","window_values":[...]}'
   ```

문제가 생기면 [`ml_step1_infra.md`](ml_step1_infra.md) 의 "알려진 제약" 섹션을 먼저 확인하세요.
