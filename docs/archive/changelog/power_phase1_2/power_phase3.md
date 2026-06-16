# 전력 임계치 Phase 3 — IF 학습 데이터 인프라 (라벨링 + 시나리오 5종)

> **요약 한 줄**: 더미 시뮬레이터를 "균등 난수" → "채널 정격 + 시간대별 base_load + 시나리오 5종(상태머신)"으로 재구성하고, PowerData에 `is_anomaly`/`anomaly_type` 라벨을 추가해 STEP B(sklearn IsolationForest)의 학습 가능한 데이터셋을 생산한다.

**브랜치**: `feature/power_refactory` (Phase 1+2 후속) · **커밋**: 1개 (`c6f773b`) · **상세 plan**: [skill/plan/power-threshold-roadmap.md](../../../../skill/plan/power-threshold-roadmap.md) §3단계 (gitignore 영역) · **선행 정리**: [skill/planB/power-phase1-2-followups.md](../../../../skill/planB/power-phase1-2-followups.md) #G

---

## 왜 이 작업을 했나

### 기존 동작의 한계 (IF 학습 관점)

| 항목 | Phase 1+2 시점 | IF 학습용 한계 |
|---|---|---|
| 더미 분포 | `random.randint(50, 5000)` 균등 | 정상 패턴이 형성되지 않음 — IF가 "outlier"를 정의할 baseline 없음 |
| 시계열 자기상관 | 없음 (틱간 독립) | "정상 → 사고 진입 → 회복"의 연속 변화 학습 불가 |
| 멀티변수 상관 | 없음 (W·A·V 독립 샘플링) | 모터 과부하 시 "W↑·A↑·V↓ 동시" 같은 도메인 패턴 부재 |
| 정상/이상 라벨 | 없음 | 평가 시 detection rate / false negative 측정 불가 |
| 시나리오 개념 | 없음 | "어떤 사고 유형이 어떤 가중치"로 발생하는지 모델링 불가 |

### 코드 검토에서 확인한 결함 5가지

| # | 문제 | 위치 | 영향 |
|---|---|---|---|
| 1 | `power_dummy.generate_*_data()`가 균등 난수만 생성 | [`fastapi-server/dummies/power_dummy.py`](../../../../fastapi-server/dummies/power_dummy.py) (변경 전) | IF 학습 부적합 |
| 2 | `PowerData`에 라벨 필드 부재 | [`drf-server/apps/monitoring/models/power_data.py`](../../../../drf-server/apps/monitoring/models/power_data.py) | 평가 단계 시나리오 매칭 불가 |
| 3 | `_PowerMeasurementBase`에 라벨 통과 경로 없음 | [`fastapi-server/power/schemas/power.py`](../../../../fastapi-server/power/schemas/power.py) | 시뮬레이터 라벨이 DB까지 도달 못 함 |
| 4 | `ALLOWED_MODES`가 4종(mixed/normal/warning/danger)뿐 | [`fastapi-server/internal/routers/scenario_router.py`](../../../../fastapi-server/internal/routers/scenario_router.py) + [`dummies/_scenario.py`](../../../../fastapi-server/dummies/_scenario.py) | 시나리오 격리 테스트 불가 |
| 5 | 가스 dummy v2의 알려진 단점(시계열 자기상관 없음, 균등 분포) | [`fastapi-server/dummies/gas_dummy.py`](../../../../fastapi-server/dummies/gas_dummy.py) v2 회고 | 전력에서 동일 실수 반복 가능 |

### 가스 v2 패턴과의 관계

가스 dummy v2는 시나리오 4종(co_leak/h2s_leak/fire/chemical_spill)을 도입해 **멀티변수 상관 패턴**을 처음 구현했다 ([`gas_dummy.py`](../../../../fastapi-server/dummies/gas_dummy.py) §SCENARIOS). 그러나 두 가지 알려진 단점:

1. **시계열 자기상관 부재** — 매 틱이 독립 균등 샘플, "정상→사고→회복" 흐름 없음
2. **시나리오 균등 분포** — `random.choice` 25% 균등, 실제 사고 빈도 무관

본 Phase 3는 두 단점을 **상태머신 + `random.choices` 가중치**로 보완하고, 전력에서 검증된 구조를 향후 가스 plan에서 재사용할 수 있도록 도메인 비종속 헬퍼(`_state_machine.py`)로 분리한다.

---

## 핵심 결정사항

| 결정 사항 | 채택안 | 근거 |
|---|---|---|
| 라벨 저장 위치 | **PowerData에 `is_anomaly`/`anomaly_type` 컬럼 추가** | row 단위 시계열 필터(`WHERE is_anomaly=True`)가 가능. JSON 컬럼은 인덱스 불가 |
| 라벨 전달 경로 | **`_PowerMeasurementBase.anomaly_labels` 옵션 필드 → 라우터 → 시리얼라이저 통과** | 운영 장비 페이로드는 미전송, 시뮬레이터만 채움 → 운영/시뮬레이터 동일 라우터로 처리 |
| 상태머신 위치 | **`fastapi-server/dummies/_state_machine.py` 별도 모듈 (도메인 비종속)** | 가스/위치 dummy 재사용 가능. `ChannelState` dataclass로 채널별 독립 상태 |
| 시나리오 가중치 | **`random.choices(weights=[6,4,2,2,1])` for overload/voltage_drop/spike/phase_loss/degradation** | roadmap §3-5 도메인 지식 초기값. 운영 데이터 축적 후 보정 가능 |
| 시나리오 모드 화이트리스트 | **dummy `_scenario.py` + scenario_router 둘 다 확장 (중복 정의 유지)** | dummy는 polling 응답 검증용, router는 입력 화이트리스트. 별도 책임. 공통 모듈 추출은 후속 정리 |
| 시뮬레이터 채널 정격 출처 | **dummy 모듈 안에 하드코딩** ([`migrations/0017_seed_power_channel_meta.py`](../../../../drf-server/apps/facilities/migrations/0017_seed_power_channel_meta.py)과 동일) | dummy는 fastapi 컨테이너에서 동작 — channel_meta_cache 의존하면 booting race. 명시적 복제 + 동기화 책임 주석 |
| 라벨 적용 범위 | **RAMP_UP 구간도 `is_anomaly=True` 라벨** | IF 학습 데이터에서 전이 구간을 "정상→이상 전조"로 학습하게 함 |

---

## 단계별 변경 (C1~C6)

본 커밋은 단일 PR로 묶었으나, 로직상 6단위로 분할 가능. 문제 발생 시 단위별 분석에 사용.

### C1 — PowerData 라벨 필드 (`is_anomaly`/`anomaly_type`) + 마이그 0006

**무엇**
- 수정 [drf-server/apps/monitoring/models/power_data.py](../../../../drf-server/apps/monitoring/models/power_data.py)
  - `AnomalyType` TextChoices 5종(overload/voltage_drop/spike/phase_loss/degradation)
  - `is_anomaly` (BooleanField, default=False, verbose+help_text)
  - `anomaly_type` (CharField, choices, nullable, blank=True)
  - 신규 인덱스 `idx_pwr_anomaly_time` (is_anomaly, -measured_at) — IF 학습 데이터 추출 쿼리 가속
- 신규 [drf-server/apps/monitoring/migrations/0006_powerdata_is_anomaly_anomaly_type.py](../../../../drf-server/apps/monitoring/migrations/0006_powerdata_is_anomaly_anomaly_type.py)

**왜**
- IF 학습 입력: `WHERE is_anomaly=False AND value > 0` 정상 데이터셋 추출
- IF 평가 입력: `WHERE is_anomaly=True` + `anomaly_type` 라벨로 시나리오별 detection rate 측정
- 운영 환경에서는 두 필드 모두 기본값(False/None) — 운영자가 사후 라벨링 시에도 같은 필드 재사용 가능

**검증**
```bash
docker exec diconai-drf-1 python manage.py migrate monitoring   # [X] 0006 적용
docker exec diconai-drf-1 python manage.py shell -c "
from apps.monitoring.models import PowerData
fields = [(f.name, f.__class__.__name__) for f in PowerData._meta.get_fields()]
print([f for f in fields if 'anomaly' in f[0]])
# [('is_anomaly', 'BooleanField'), ('anomaly_type', 'CharField')]
"
```

---

### C2 — DRF 시리얼라이저 라벨 통과 경로

**무엇**
- 수정 [drf-server/apps/monitoring/serializers/power_data.py](../../../../drf-server/apps/monitoring/serializers/power_data.py)
  - `_ChannelEntrySerializer`에 `is_anomaly`/`anomaly_type` (required=False, default=False/None)
  - `PowerDataBulkIngestSerializer.create()`이 두 필드를 PowerData 인스턴스에 매핑
  - docstring 보강 — 두 필드가 더미 시뮬레이터 전용임 명시

**왜**
- FastAPI → DRF 한 경로로 운영/시뮬레이터 모두 처리. 시뮬레이터 페이로드만 anomaly 정보를 갖고, 운영은 기본값으로 빈 row 저장
- `required=False`라 기존 운영 페이로드 호환 (회귀 없음)

---

### C3 — `_state_machine.py` 신설 (NORMAL/RAMP_UP/HOLD/RAMP_DOWN FSM)

**무엇**
- 신규 [fastapi-server/dummies/_state_machine.py](../../../../fastapi-server/dummies/_state_machine.py)
  - `ChannelState` dataclass — 채널 1개의 상태(`state`, `scenario`, `ticks_in_state`, ramp/hold 길이)
  - `StateOutput` dataclass — step() 결과(`scenario_weight`, `is_anomaly`, `anomaly_type`)
  - `enter_scenario(cs, scenario, ramp_up_ticks, hold_ticks, ramp_down_ticks)` — NORMAL → RAMP_UP 진입 (이미 진행 중이면 무시)
  - `step(cs)` — 1틱 진행 + 자동 상태 전이. weight 0→1 (RAMP_UP), 1.0 (HOLD), 1→0 (RAMP_DOWN), 0.0 (NORMAL)
  - `maybe_trigger(cs, probability, scenarios, weights, hold_ticks_by_scenario, ...)` — NORMAL 상태일 때 probability로 가중치 무작위 시나리오 진입
  - `mix(normal_value, scenario_value, weight)` — 선형 보간 헬퍼

**왜**
- 가스 v2 단점 #1(시계열 자기상관 없음) 해결의 핵심 — IF가 "연속적 변화"를 학습할 수 있게 함
- 도메인 비종속 — 가스/위치 dummy plan에서 그대로 재사용
- 채널별 독립 상태로 멀티 채널 동시 시나리오 진입 지원

**검증**
```python
cs = ChannelState()
enter_scenario(cs, 'overload', ramp_up_ticks=3, hold_ticks=4, ramp_down_ticks=2)
# 12틱 step() 호출 → ramp_up(0.33→1.0) → hold(1.0×4) → ramp_down(0.5→0) → normal
# 모든 ramp/hold 구간에서 is_anomaly=True 보장
```

---

### C4 — `power_dummy.py` v3 전면 재작성

**무엇**
- 수정 [fastapi-server/dummies/power_dummy.py](../../../../fastapi-server/dummies/power_dummy.py) (+340 / -91 라인)
  - **`CHANNEL_RATED` 16채널 정격 하드코딩** — [0017_seed_power_channel_meta.py](../../../../drf-server/apps/facilities/migrations/0017_seed_power_channel_meta.py)와 동일 (변경 시 양쪽 동시 수정 책임 주석)
  - **`MOTOR_CHANNELS`/`LIGHTING_CHANNELS`/`PANEL_CHANNELS`** 분류 — 시나리오 적용 대상 결정
  - **`base_load_ratio(hour, ch)`** — 채널 종류·시간대 기저 부하 비율 (모터 08-12시 60%, 13-18시 70%, 야간 15%; 조명 40%; 분전반 50%)
  - **`SCENARIO_PATTERNS` 5종** — (w_factor, a_factor, v_factor, ramp_up, hold, ramp_down) 매핑
    - overload: 정격 110% (W·A) + 93%(V 동반 강하), hold 60틱
    - voltage_drop: V↓ 88% + W·A 보상, multi=True (16채널 동시), hold 30
    - spike: 130% 매우 짧음, hold 1
    - phase_loss: ~0 (결상), hold 30
    - degradation: 점진 ramp_up 60 + 105%, 천천히
  - **`SCENARIO_WEIGHTS = [6, 4, 2, 2, 1]`** — `random.choices` 가중치 (roadmap §3-5)
  - **`MIXED_TRIGGER_PROBABILITY = 0.005`** — 16채널 × 0.005 = 평균 12.5틱당 1건 시나리오 진입
  - **`_channel_states`** — 채널별 상태 (프로세스 메모리)
  - **`_compute_channel_tick(ch, hour)`** — 정상값(정격×base×노이즈) ↔ 시나리오값(정격×factor×약한노이즈)를 weight로 mix
  - **`_apply_mode(mode)`** — mixed면 `maybe_trigger`, 단일 시나리오면 `enter_scenario` 강제, FIXED면 상태머신 미사용
  - **`_fixed_level_value(ch, level)`** — normal/warning/danger 모드 즉시 산출 (UI/알람 테스트용)
  - **`_build_tick()`** — 매 틱 16채널 (W,A,V,onoff) 한 번에 계산 후 4개 페이로드(onoff/current/voltage/watt) 분배 + anomaly_labels 동봉

**왜**
- 가스 v2의 멀티변수 상관 패턴(`_build_scenario_levels`)을 전력에 1:1 대응 + 단점 보완
- 한 틱 = 한 시점 → 4축이 같은 시나리오 상태에서 계산되어 W·A·V가 도메인적으로 일관됨 (가스 v2의 가스별 독립 샘플링 → 멀티변수 상관 명시화)
- 모드별 분기 깔끔: mixed(IF 학습용) / fixed(UI 테스트) / single(시나리오 격리 테스트) 셋이 단일 함수 흐름

**검증 (1개 단위 — 격리 테스트)**
```python
_channel_states = {ch: ChannelState() for ch in range(1, 17)}
_apply_mode('overload')
# → 모터 채널 1개(random.choice(MOTOR_CHANNELS))에 overload 시나리오 진입
w, a, v, onoff, is_anom, anom_type = _compute_channel_tick(3, hour=10)
# (예) ch3: W=1886.4 A=7.51 V=378.1 type=overload (RAMP_UP 1틱 시점, 가중치 낮음)
```

---

### C5 — FastAPI 페이로드 anomaly 라벨 통과

**무엇**
- 수정 [fastapi-server/power/schemas/power.py](../../../../fastapi-server/power/schemas/power.py)
  - `_PowerMeasurementBase.anomaly_labels: dict[str, str] | None = None` 옵션 필드
  - `to_anomaly_map() -> dict[int, str]` 메서드 (str 키 → int 변환)
- 수정 [fastapi-server/power/services/power_service.py](../../../../fastapi-server/power/services/power_service.py)
  - `to_channel_list(channel_values, anomaly_map=None)` 시그니처 확장
  - 채널 entry 생성 시 `is_anomaly`/`anomaly_type` 포함
- 수정 [fastapi-server/power/routers/power_router.py](../../../../fastapi-server/power/routers/power_router.py)
  - `recv_current` / `recv_voltage` / `recv_watt` 세 라우터가 `payload.to_anomaly_map()` 호출
  - `recv_onoff`는 변경 없음 (ON/OFF는 라벨 불필요)

**왜**
- 단일 페이로드 schema가 운영(`anomaly_labels=None`)과 시뮬레이터(`anomaly_labels={"1": "overload"}`) 모두 수용
- pydantic v2 기본 `extra=ignore`이므로 모르는 필드 전송 시에도 운영 안전

---

### C6 — 시나리오 모드 화이트리스트 확장 (5종 추가)

**무엇**
- 수정 [fastapi-server/dummies/_scenario.py](../../../../fastapi-server/dummies/_scenario.py)
  - `ALLOWED_MODES`에 5종 추가 (`overload`, `voltage_drop`, `spike`, `phase_loss`, `degradation`)
  - 코멘트: 가스/위치 더미는 fallback("mixed") 처리
- 수정 [fastapi-server/internal/routers/scenario_router.py](../../../../fastapi-server/internal/routers/scenario_router.py)
  - `ALLOWED_MODES` 동일하게 확장 (입력 화이트리스트)
  - 모듈 상단 코멘트 + GET/POST description에 9종 모드 반영 (OpenAPI 자동 문서 갱신)

**왜**
- 검증 단계에서 `POST /internal/scenario/mode {"mode":"overload"}`가 422로 막혔던 버그 해결
- 단일 시나리오 모드는 IF 학습 데이터 격리 테스트(시나리오별 detection rate 측정)에 필수

**알려진 책임 분리 노트**
- `ALLOWED_MODES`가 두 파일에 중복 정의됨 — 한쪽은 polling 응답 검증(dummy 측), 다른 쪽은 입력 화이트리스트(router 측). 책임은 분리되어 있지만 동기화 책임은 운영자에게 위임. 공통 모듈 추출은 후속 정리 항목.

---

## 검증 결과 (전체)

### 회귀 — Phase 1+2 평가 함수가 무회귀임 증명

```bash
docker exec diconai-drf-1 python -m pytest \
    apps/facilities/tests/test_evaluate_power_axes.py \
    apps/monitoring/tests/test_power_alarm_axis_combine.py \
    apps/monitoring/tests/test_power_alarm_flow.py \
    -v
# 20 passed (5.21s) — 평가 로직 무회귀 확정
```

### overload 격리 테스트 (90초)

| 항목 | 결과 |
|---|---|
| total row | 7872 (≈ 90s × 16ch × 3축 × 1.8 송신중복) |
| anomaly row | 4599 (58%) — 모터 11채널 시나리오 누적 진입 |
| data_type 분포 | current/voltage/watt 각 1533 (정확히 1:1:1) — 3축 동시 라벨 ✓ |
| 채널 분포 | 모터(1-8, 12-14)에만 적재, 분전반(9,10,11,16)·조명(15) 제외 ✓ |
| 시나리오 라벨 | 100% `overload` ✓ |

### mixed 5분 — 가중치 분포 + IF 학습 데이터 가용량

| 시나리오 | 가중치 | hold/ramp | 단순 가중치 % | 실측 % | 해석 |
|---|---|---|---|---|---|
| overload | 6 | hold 60 | 40% | **49.1%** | 긴 HOLD로 라벨 누적 ↑ |
| voltage_drop | 4 | hold 30, multi 16ch | 27% | **18.9%** | 짧은 hold + multi 트리거 상쇄 |
| phase_loss | 2 | hold 30 | 13% | **20.8%** | 단일 채널 hold 누적 |
| degradation | 1 | ramp_up 60 | 7% | **8.3%** | 긴 RAMP_UP으로 비율 유지 |
| spike | 2 | hold 1 | 13% | **2.8%** | 매우 짧은 hold (가스 v2 균등 분포 한계 해결 ✓) |

**적재량 (15시간 mixed 누적)**
- 정상(IF 학습용, `value > 0`): **263,114**
- 라벨(평가용): **9,768**
- 시나리오별 ≥ 100건: overload(8112)·phase_loss(660)·voltage_drop(642)·degradation(264)·spike(90)
- 학습 시작 조건(정상 ≥ 1000 + 라벨 ≥ 500): **충족 ✓**

### 임계치 알람 회귀 (Phase 2 발화 정상)

| 시간 범위 | AlarmRecord | 분포 |
|---|---|---|
| 최근 10분 | 21건 | DANGER 16 + WARNING 5 — 시나리오 진입 시 정격 110% 도달 시점에 발화 ✓ |

---

## 알려진 제약사항 / 후속 작업

| # | 항목 | 본 PR 처리 | 후속 |
|---|---|---|---|
| 1 | `fastapi-server` 컨테이너에 `requests` 모듈 부재 (dummy 의존성) | 검증 시 임시 `pip install` | `fastapi-server/pyproject.toml`에 추가 + 재빌드 (별도 PR) |
| 2 | `drf-server` 컨테이너에 `pytest`/`pytest-django` 부재 (dev 의존성) | 검증 시 임시 `pip install` | dev 의존성 정리 (별도 PR) |
| 3 | `ALLOWED_MODES`가 두 파일에 중복 정의 | 양쪽 모두 9종으로 동기화 (책임 분리 유지) | 공통 상수 모듈 추출 (별도 정리 sprint) |
| 4 | 단일 시나리오 모드 진입 시 매 틱 random.choice로 결국 모터 11채널 다 점유 | 의도(IF 학습용은 라벨 다양성↑) | "한 채널만 격리" 가 필요하면 lock 옵션 추가 |
| 5 | `degradation` 시나리오 ramp_up 60틱(60s) — dummy 1초 간격 기준 1분 | 의도된 길이 (점진 열화 시뮬레이션) | 운영 데이터 축적 후 hold/ramp 파라미터 보정 |
| 6 | IF 이상탐지 미적용 | `apps/ml/` 미존재 | **Phase 4 (STEP B) — 본 PR이 학습 데이터 확보** |
| 7 | 지속시간 카운터 / 히스테리시스 | 미적용 | Phase 5 — IF anomaly 분포 확보 후 결정 |

---

## 단계 간 의존성

```
C1 (PowerData 라벨 필드) ─┬─→ C2 (시리얼라이저)
                          │
C3 (_state_machine.py) ──┴───┬─→ C4 (power_dummy v3)
                              │
                              C5 (FastAPI 페이로드 통과) ──→ C6 (시나리오 모드 확장)
```

- C1·C3 병렬 가능
- C2는 C1 의존, C4는 C3 의존
- C5는 C4의 anomaly_labels 송신을 받기 위한 수신 경로 → 동시 필요
- C6는 단일 시나리오 모드 송신을 위한 prerequisite (분리 가능하나 한 PR로 함께)

---

## 변경 파일 요약

| 영역 | 파일 | 변경 유형 | 라인 |
|---|---|---|---|
| DRF 모델 | `monitoring/models/power_data.py` | 라벨 필드 + 인덱스 추가 | +21 |
| DRF 마이그 | `monitoring/migrations/0006_powerdata_is_anomaly_anomaly_type.py` | 신규 | +49 |
| DRF 시리얼라이저 | `monitoring/serializers/power_data.py` | 라벨 통과 + docstring | +14 |
| FastAPI 더미 | `dummies/_state_machine.py` | 신규 FSM 모듈 | +149 |
| FastAPI 더미 | `dummies/power_dummy.py` | v3 전면 재작성 | +340 / -91 |
| FastAPI 더미 | `dummies/_scenario.py` | ALLOWED_MODES 확장 | +13 |
| FastAPI 라우터 | `internal/routers/scenario_router.py` | 화이트리스트 + OpenAPI description | +41 |
| FastAPI 라우터 | `power/routers/power_router.py` | anomaly_map 전달 | +6 |
| FastAPI 스키마 | `power/schemas/power.py` | anomaly_labels + to_anomaly_map() | +11 |
| FastAPI 서비스 | `power/services/power_service.py` | to_channel_list 시그니처 확장 | +10 |

**총**: 10 files changed, 603 insertions(+), 75 deletions(-) — 커밋 `c6f773b`

---

## STEP B 진입점 (다음 작업)

본 Phase 3가 제공한 학습 데이터 인프라 위에서 진행:

1. `drf-server/apps/ml/` Django 앱 신설 — `MLModel`, `MLAnomalyResult`
2. `services/dataset_service.py` — `extract_normal_dataset(since, channels, axes)` (`is_anomaly=False AND value > 0`)
3. `services/feature_service.py` — roll_mean / roll_std / diff 파생변수
4. `management/commands/train_anomaly_model` — sklearn IsolationForest 학습 → `media/ml_models/power_if_v1.pkl`
5. `fastapi-server/ai/router.py` — `POST /ai/predict`

상세 가이드: [skill/plan/if-integration-guide.md](../../../../skill/plan/if-integration-guide.md)
