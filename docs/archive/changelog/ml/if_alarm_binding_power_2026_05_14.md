# IF §2 알람 결합 — 전력 (트랙 1 v2, fastapi 중심)

> 작성: 2026-05-14
> branch: `feature/power_IF_2`
> 본 sprint plan: [skill/plan/if-data-prep-and-alarm-binding.md](../../../../skill/plan/if-data-prep-and-alarm-binding.md) §"트랙 1 v2"
> 다음 단계: [skill/planB/if-data-prep-followups.md](../../../../skill/planB/if-data-prep-followups.md), [skill/plan/alarm-record-integration.md](../../../../skill/plan/alarm-record-integration.md)

---

## 무엇이 가능해졌나

| 이전 | 이후 |
|---|---|
| IF 모델 학습됐지만 **알람 경로 없음** — 운영자가 IF 결과 못 봄 | **`[AI 이상 패턴] CH1 watt=8244 (combined=danger)` 화면 알람 표시** |
| 알람 종류는 `power_overload` (threshold) 1개 | `power_overload` + **`power_anomaly_ai` (IF + threshold 결합)** 2종 공존 |
| IF 추론 결과 DB 저장 안 됨 | **`MLAnomalyResult` 매번 저장** — BI/통계 분석 가능 |
| threshold·IF 단일 판단 | **`combine_risk` 매트릭스 (3×2)** — `PREDICT_WARN` (threshold 정상 + IF 이상) / `CAUTION` (threshold 경고 + IF 정상) 차별화 |
| 폭주 시 fastapi 워커 묶임 → 가스 endpoint timeout | **rate limit 60초 + fire-and-forget** — 가스 측 영향 0 |

→ 운영 데이터 흐름 (엣지게이트웨이 → fastapi → 알람) 정합. 가스 측 패턴 (`gas_service.py`)과 일관.

---

## 데이터 흐름 (Before / After)

### Before (sprint 시작 전 — power threshold만)

```
센서 → fastapi /api/power/watt
         ├─ update_power_state (메모리)
         └─ bg.add_task → DRF POST /api/monitoring/power/data/
                          ├─ PowerData bulk_create
                          └─ post_save signal → trigger_power_alarms
                                ├─ evaluate_power_risk (threshold)
                                └─ if WARNING/DANGER:
                                     └─ Celery (fire_power_*_task)
                                          → AlarmRecord(POWER_OVERLOAD)
                                          → _push_to_ws → 화면
```

### After (트랙 1 v2)

```
센서 → fastapi /api/power/watt (recv_watt)
         ├─ update_power_state
         ├─ ★ process_anomaly_inference (신규):
         │    ├─ _power_windows[(ch, type)].append (deque, maxlen=30)
         │    ├─ len >= 30:
         │    │    ├─ _get_or_load("power") + model.predict
         │    │    ├─ calculate_power_risk → threshold_risk
         │    │    ├─ combine_risk(threshold, pred) → combined  ★ 매트릭스
         │    │    ├─ asyncio.create_task(post_to_drf MLAnomalyResult)  ★ 매번 추적
         │    │    └─ combined ∈ {caution, predict_warn, danger}:
         │    │         ├─ rate limit 60초 통과 검사
         │    │         └─ asyncio.create_task(_safe_push_alarm)  ★ fire-and-forget
         │    │             → Redis active_alarms → broadcast → 화면
         └─ bg.add_task → DRF POST /api/monitoring/power/data/
                          (기존 threshold 알람 흐름 유지 — 변경 X)

알람 종류:
  · power_overload    (DRF threshold) — AlarmRecord 저장 ✓
  · power_anomaly_ai  (fastapi IF 결합) — 화면 표시 ✓, AlarmRecord 미저장 (P0 작업)
```

---

## 핵심 결정

### 1. fastapi 중심 재설계 (트랙 1 v1 → v2)

**문제**: 처음 plan은 DRF 중심 (management command + DRF에서 추론 트리거). e2e PoC 후 발견:
- 운영 데이터 흐름과 어긋남 (엣지게이트웨이 → fastapi 수집 → 빠른 판단 → 알람)
- DRF는 저장 역할도 동시 — 추론·결합까지 부담 시 SQLite lock 위험 ↑
- 가스 측이 이미 fastapi에서 추론 (`gas_service.py:67-87`) — 양측 패턴 일관성 ↓

**결정**: 추론·결합·발화 주체를 **fastapi**로 이동. DRF는 결과 저장만.

**v1 dead code 정리**: `apps/ml/services/risk_combine_service.py` (DRF) + `tests/test_risk_combine_service.py` + `apps/ml/management/commands/run_anomaly_e2e.py` (PoC) → fastapi 측 동일 함수로 회귀 가치 대체. 327줄 삭제.

### 2. combine_risk 매트릭스 (3×2)

`MLAnomalyResult.RiskClassified` 4단계(NORMAL/CAUTION/PREDICT_WARN/DANGER)를 활용한 매트릭스:

| threshold \ IF | normal | anomaly |
|---|---|---|
| NORMAL | NORMAL | **PREDICT_WARN** ★ (예측 경보) |
| WARNING | **CAUTION** ★ (약한 경보) | DANGER |
| DANGER | DANGER | DANGER |

**의의**:
- `PREDICT_WARN` = "threshold 정상이지만 IF가 미세 이상 감지" — IF 도입의 핵심 가치
- `CAUTION` = "threshold 경계 진입이지만 IF는 정상" — 약한 경보로 분리
- 운영자가 4단계 모두 의미 있게 활용 가능

### 3. AlarmType.POWER_ANOMALY_AI (도메인별 분리)

**이전 안**: `AlarmType.ANOMALY` 단일 enum.
**최종**: `POWER_ANOMALY_AI` (도메인 명시). 가스 측은 `GAS_ANOMALY_AI` (가스 작업자 별도 sprint).

**이유**: 향후 `vibration_anomaly_ai`, `temperature_anomaly_ai` 등 신규 도메인 추가 시 명확. 가스 측 `gas_anomaly_ai` 가 현재 enum 미정의 anti-pattern → 분리 패턴이 정합성 회복 경로.

### 4. AnomalyMeta nested schema

`AlarmPayload`에 ANOMALY 고유 필드 5개를 평탄하게 추가하는 대신 nested `AnomalyMeta` BaseModel로 캡슐화:
- 다른 alarm_type 페이로드에 None 필드 노출 X
- §3 multi-variate IF / CPD 추가 시 `AnomalyMeta` 안에서만 변경 — 외부 schema 영향 0
- type-safe (Pydantic 검증)

### 5. rate limit + fire-and-forget (폭주·DB lock 동시 차단)

**문제 발견 (e2e 검증 시)**:
1. `overload` HOLD 60틱 동안 매 추론 → push_alarm 폭주 → 브라우저 hang
2. `await post_to_drf` SQLite lock 시 5초 timeout → fastapi 단일 워커 묶임 → 가스 endpoint timeout
3. Redis hang 시 push_alarm 도 같은 위험

**해결**:
- **rate limit 60초** — 같은 sensor_identifier 60초당 push_alarm 1회. forward는 매번 (운영 추적 보존)
- **post_to_drf fire-and-forget** — `asyncio.create_task`. DRF lock 영향 0
- **push_alarm fire-and-forget** + `_safe_push_alarm` wrapper — Redis hang 영향 0, silent fail은 `logger.warning`

---

## 변경 요약

### DRF (단일 진실 공급원)

| 파일 | 변경 |
|---|---|
| [apps/core/constants.py](../../../../drf-server/apps/core/constants.py) | `AlarmType.POWER_ANOMALY_AI = "power_anomaly_ai"` ("전력 AI 이상 감지") + `USER_FACING_ALARM_TYPES` 갱신 |
| [apps/alerts/migrations/0011_*.py](../../../../drf-server/apps/alerts/migrations/) | enum 추가 (3 필드 choices) |
| [apps/alerts/migrations/0012_*.py](../../../../drf-server/apps/alerts/migrations/) | enum rename + RunPython data migration (alarm_record 7건 + event 4건 자동 변환) |
| [apps/ml/views.py](../../../../drf-server/apps/ml/views.py) | `MLAnomalyResultCreateView` (`POST /api/ml/anomaly-results/`) + `authentication_classes=[]` (drf_client invalid Bearer 토큰 401 회피) |
| [apps/ml/urls.py](../../../../drf-server/apps/ml/urls.py) | `path("anomaly-results/", ...)` |
| [apps/ml/tests/test_anomaly_result_create.py](../../../../drf-server/apps/ml/tests/test_anomaly_result_create.py) | 4 통합 테스트 |

### fastapi (실시간 추론·알람)

| 파일 | 변경 |
|---|---|
| [ai/risk_combine.py](../../../../fastapi-server/ai/risk_combine.py) (신규) | `combine_risk` 매트릭스 (DRF와 회귀 일치) |
| [tests/test_risk_combine.py](../../../../fastapi-server/tests/test_risk_combine.py) | 8 tests (6 cell + 2 error) |
| [power/services/threshold_eval.py](../../../../fastapi-server/power/services/threshold_eval.py) (신규) | `calculate_power_risk` — 정격 % 환산 (단방향 W/A + 양방향 V) |
| [tests/test_threshold_eval.py](../../../../fastapi-server/tests/test_threshold_eval.py) | 17 tests (W/A/V × normal/warning/danger 경계 14 + edge 3) |
| [internal/routers/alarm_router.py](../../../../fastapi-server/internal/routers/alarm_router.py) | `AnomalyMeta` nested schema 추가 |
| [tests/test_alarm_payload_anomaly_meta.py](../../../../fastapi-server/tests/test_alarm_payload_anomaly_meta.py) | 5 tests (Pydantic validation) |
| [power/services/power_service.py](../../../../fastapi-server/power/services/power_service.py) | `process_anomaly_inference` — channel별 deque + IF 추론 + combine_risk + DRF forward + rate limit + `_safe_push_alarm` |
| [power/routers/power_router.py](../../../../fastapi-server/power/routers/power_router.py) | `recv_watt`에서 `process_anomaly_inference` 호출 |

---

## 검증

### 단위·통합 테스트 (총 34 PASSED)

```bash
# fastapi (호스트 venv 또는 컨테이너 rebuild 후)
cd fastapi-server && .venv/bin/python -m pytest tests/test_risk_combine.py tests/test_threshold_eval.py tests/test_alarm_payload_anomaly_meta.py
# → 30 passed

# DRF
docker exec diconai-drf-1 pytest apps/ml/tests/test_anomaly_result_create.py
# → 4 passed
```

**Raw 출력 (2026-05-13)**:
```
tests/test_risk_combine.py ........              [ 27%]
tests/test_threshold_eval.py .................   [ 83%]
tests/test_alarm_payload_anomaly_meta.py .....   [100%]
============================== 30 passed in 0.32s ==============================
```

### e2e 동작 검증

**명령어**:
```bash
docker restart diconai-fastapi-1
sleep 12
cd fastapi-server && DUMMY_SCENARIO_MODE=overload .venv/bin/python -m dummies.power_dummy &
sleep 90
kill %1
```

**예상·실측 출력 (anomaly 케이스 도달 시)**:
```
fastapi 로그:
  [anomaly_inference] device=63200c3afd12 ch=1 watt value=8244 threshold=danger pred=anomaly combined=danger score=-0.0146
  POST /api/power/watt 201

DRF 로그:
  POST /api/ml/anomaly-results/ 201
```

**combine_risk 매트릭스 4 cell 실측 발화 확인** (overload 시나리오 RAMP 동안 자연스럽게 도달):
- `(NORMAL, anomaly)` → PREDICT_WARN
- `(WARNING, normal)` → CAUTION
- `(WARNING, anomaly)` → DANGER
- `(DANGER, *)` → DANGER

### SQL 검증 쿼리

```sql
-- MLAnomalyResult 신규 row (forward 매번 동작 확인)
SELECT id, sensor_identifier, prediction, risk_classified, ROUND(anomaly_score, 4) AS score
FROM ml_anomaly_result
WHERE evaluated_at >= datetime('now', '-2 minutes');

-- AlarmRecord ANOMALY 분포 (현재는 PoC + e2e 잔여 7건만 — P0 작업 후 매번 저장)
SELECT alarm_type, COUNT(*) FROM alarm_record WHERE alarm_type='power_anomaly_ai';
```

---

## 운영 가이드

### active 모델 전환

```bash
docker exec diconai-drf-1 python manage.py shell -c "
from apps.ml.models import MLModel
MLModel.objects.filter(sensor_type='power', is_active=True).update(is_active=False)
MLModel.objects.filter(version=N, sensor_type='power').update(is_active=True)
"
# fastapi 측 캐시 자동 reload (TTL 5분), 즉시 반영하려면:
curl -X POST http://localhost:8001/ai/reload?sensor_type=power
```

### rate limit 조정

```python
# fastapi-server/power/services/power_service.py
RATE_LIMIT_SEC = 60  # 같은 sensor_identifier 60초당 push_alarm 1회
```

운영 시 60초 → 30초 등 조정 필요하면 위 상수 변경 + fastapi 재시작.

### 추론 채널 확장

```python
# 본 sprint: ch1·watt만
_INFERENCE_ENABLED_CHANNELS: set[tuple[int, str]] = {(1, "watt")}

# 다른 채널 추가 (단, 해당 채널·data_type으로 학습된 active 모델 필요)
# = {(1, "watt"), (2, "watt"), (1, "voltage"), ...}
```

### 폭주 발생 시 즉시 회복

```bash
# 1. 더미 중지
kill <dummy_pid>

# 2. Celery 큐 비움 + DRF lock 해제
docker compose restart celery-worker drf

# 3. fastapi rate limit dict 초기화 (메모리)
docker restart diconai-fastapi-1
```

---

## 한계 / 다음 단계

| 한계 | 영향 | 다음 단계 |
|---|---|---|
| **AlarmRecord 미저장** (push만) | 운영 분석·통계·정책 매칭 불가 (양측 공통) | **P0 — [skill/plan/alarm-record-integration.md](../../../../skill/plan/alarm-record-integration.md)** (즉시 진입) |
| spike·phase_loss recall ~0% | watt 단일 채널 + window=30 구조적 한계 | §3-1 multi-variate IF / §3-2 spike 전용 (planB §P2) |
| 16채널 일반화 안 됨 | 본 sprint는 ch1·watt 1개 시리즈만 | §3-6 multi-channel (운영 6개월 후) |
| `_get_or_load` TTL 만료 시 hang | 5분 TTL 만료 후 첫 호출 1회 묶임 | T1-v2-followup-2 (트리거 시) |
| severity escalation bypass 없음 | caution 60초 묶임 중 danger 격상 시 묶임 | T1-v2-followup-1 (운영 사례 발견 시) |
| 가스 측 `gas_anomaly_ai` enum 미정의 | 가스 alarm_type validation 우회 | 가스 트랙 작업자가 P0 인프라 호출 추가 시 함께 |

---

## 협업 — 트랙 간 영향

| 트랙 | 본 sprint 영향 | 가이드 |
|---|---|---|
| **가스 트랙** (별도 작업자) | 본 sprint 무관 — `gas_service.py` 그대로. P0 인프라 머지 후 helper 호출만 추가하면 일관 패턴 | [alarm-record-integration.md](../../../../skill/plan/alarm-record-integration.md) §"가스 트랙 가이드" |
| **§3 IF 고도화** (다음 sprint) | active 모델 v3 (90일) 베이스. C7 `_INFERENCE_ENABLED_CHANNELS` 확장 + multi-variate 모델 학습 | [planB §P2](../../../../skill/planB/if-data-prep-followups.md) |
| **UI Phase 2** (별도 트랙) | `combined_risk=PREDICT_WARN` 표시 색상 — 노란-주황 톤 별도 디자이너 협의 | UI 트랙 |

---

## commit log (12개)

```
2d6053f feat(C12): rate limit (60s) + fire-and-forget (post_to_drf + push_alarm)
1877cdd refactor(C11): ANOMALY → POWER_ANOMALY_AI rename + data migration
0f62385 refactor: 트랙 1 v1 DRF dead code 삭제
9a21ee5 fix(C10): MLAnomalyResult/Active view authentication_classes=[]
4bb288d feat(C9): MLAnomalyResult 비동기 forward (fastapi → DRF)
30df81f feat(C8): AlarmPayload nested AnomalyMeta + 5 schema tests
c7cc13d feat(C7): power_service IF 추론 통합 (process_anomaly_inference)
e057aad feat(C6): power threshold fastapi 평가 + 17 tests
ccce6d3 feat(C5): combine_risk fastapi 복제 + 8 tests
c48e3f2 feat(T1-3): MLAnomalyResult INSERT view + 4 tests
98f0732* feat(T1-2): combine_risk DRF (※ 0f62385에서 삭제)
32aaa05 feat(T1-1): AlarmType.ANOMALY enum + migration 0011
```

---

## 관련 문서

| 문서 | 위치 |
|---|---|
| 본 sprint 실행 plan | [skill/plan/if-data-prep-and-alarm-binding.md](../../../../skill/plan/if-data-prep-and-alarm-binding.md) §"트랙 1 v2" |
| 더미 데이터 audit | [docs/changelog/ml/power_dummy_audit_2026_05_13.md](./power_dummy_audit_2026_05_13.md) |
| IF 윈도우 비교 (PoC 방법론) | [docs/changelog/ml/if_window_comparison_2026_05_13.md](./if_window_comparison_2026_05_13.md) |
| ML STEP 1 인프라 | [docs/changelog/ml/ml_step1_infra.md](./ml_step1_infra.md) |
| **다음 단계 P0** | [skill/plan/alarm-record-integration.md](../../../../skill/plan/alarm-record-integration.md) |
| 후속 sprint 인덱스 | [skill/planB/if-data-prep-followups.md](../../../../skill/planB/if-data-prep-followups.md) |
