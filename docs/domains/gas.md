# 가스 모니터링 도메인

> 코드리뷰용 흐름 이해 문서. 관련 커밋: `a9d72a6`(파이프라인 e2e), `8fc0072`(임계치 SoT + 더미)
> 데이터 흐름: **IoT 가스센서 → fastapi(수신·검증·AI) → drf(저장·알람판정) → Celery → WebSocket**
> 가장 단순한 end-to-end 흐름이라, 전체 파이프라인 그림을 처음 잡기에 적합.

---

## 1. 파일 맵

| 레이어 | 파일 | 핵심 심볼 |
|---|---|---|
| fastapi 수신 | `gas/routers/gas_router.py` | `receive_gas_data`, `receive_device_info` |
| fastapi 스키마 | `gas/schemas/gas.py` | `GasDataPayload` + `recalculate_status`, `GasDataResponse` |
| fastapi 처리 ★ | `gas/services/gas_service.py` | `process_gas_data` (조율), `_detect_change_point`, `_co_window`/`_h2s_window`/`_co2_window` |
| fastapi 임계치 SoT | `core/gas_thresholds.py` | `GAS_THRESHOLDS`, `evaluate_single_gas`, `calculate_individual_risks`, `calculate_gas_status` |
| fastapi 상수 | `gas/constants.py` | `GAS_FIELDS`(9종), `ARIMA_GAS_FIELDS`(co/h2s/co2) |
| fastapi 더미 | `dummies/gas_dummy.py` | `generate_gas_data`, `SCENARIOS`, 상태머신 |
| drf 시리얼라이저 | `monitoring/serializers/gas_data.py` | `GasDataCreateSerializer.create` |
| drf 모델 | `monitoring/models/gas_data.py` | `GasData` (wide table), `compute_risks_from_thresholds` |
| drf 알람판정 ★ | `monitoring/services/gas_alarm.py` | `trigger_gas_alarms`, `_state_key`, `_AI_GUARDED_GASES` |
| drf 임계치(2번째) | `monitoring/utils/gas_thresholds.py` | `GAS_THRESHOLDS`, `get_threshold_value`, `GAS_UNITS`, `GAS_LABELS` |

## 2. 전체 시퀀스

```
가스센서(에어위드)  1초 주기
  │ POST /api/sensors/gas  { device_id, o2, co, co2, h2s, lel, no2, so2, o3, nh3, voc, ... }
  ▼
[fastapi] gas_router.receive_gas_data
  └─ GasDataPayload 검증 (Pydantic) + model_validator 로 status 서버 재계산
  └─ process_gas_data(payload):
       ① calculate_individual_risks(gas_values)        ← 9종 *_risk 계산
       ② co/h2s/co2 window append → 30틱 차면:
            change point 게이트 → IF 추론 → 적중 시 push_alarm + forward_inference_e2e
       ③ POST /api/monitoring/gas/  (drf 저장)
       ④ latest_gas_snapshot.update() + gas_latest["updated_at"]  ← WS broadcast 용
  ▼
[drf] GasDataCreateSerializer.create
  └─ GasData.objects.create(...)  (wide table 1행: 9측정값 + 9위험도 + raw_payload)
  └─ sensor.last_reading 갱신 (60s 스로틀)
  └─ trigger_gas_alarms(gas_data)  ← atomic 밖에서 (커밋 후 Celery 발행)
       ▼
[drf] gas_alarm.trigger_gas_alarms — 9가스 루프, 위험도별 분기
       │ DANGER 즉시 / WARNING 30s 지속 / NORMAL 정상화
       └─ fire_*_task.delay()  → [alerts 도메인]
  ▼
브라우저 (broadcast_loop 1초 틱 + alarm_flush_loop 즉시)
```

## 3. status 서버 재계산 (신뢰 경계)

센서가 보낸 `status` 는 **무시**하고 서버가 다시 계산. `gas/schemas/gas.py`:
```python
@model_validator(mode="after")
def recalculate_status(self):
    self.status = calculate_gas_status(gas_values)   # core/gas_thresholds
    return self
```
→ 센서 펌웨어를 신뢰하지 않고 서버가 단일 판정. 더 나아가 **DRF 도** raw 값만 신뢰하고 위험도를 facility별 Threshold DB 로 재계산(`GasData.compute_risks_from_thresholds`). 즉 판정이 fastapi → drf 로 가며 한 번 더 검증된다.

## 4. 임계치 SoT 이원화 ⚠️ (가장 중요한 함정)

같은 임계치가 **두 곳에 독립 존재**:
```python
# fastapi/core/gas_thresholds.py
GAS_THRESHOLDS = {"co": {"normal_max": 25, "warning_max": 200}, ...}
# drf/apps/monitoring/utils/gas_thresholds.py
GAS_THRESHOLDS = {"co": {"normal_max": 25, "warning_max": 200}, ...}   # 같은 값 복제
```
- 별도 패키지(fastapi ↔ drf)라 Python import 공유 불가 → **값 변경 시 양쪽 동시 수정 필수**. 한쪽만 고치면 fastapi 판정과 drf 저장 위험도가 어긋남.
- 9종 필드 목록도 마찬가지 — `gas/constants.py GAS_FIELDS` 가 fastapi 측 단일 정의처지만 drf `gas_alarm.GAS_FIELDS` 와 별개.

판정 로직 (`evaluate_single_gas`):
```python
if gas == "o2":   # O2 만 "낮을수록 위험" (역방향)
    if value < warning_min: return "danger"
    if value < normal_min or value > normal_max: return "warning"
    return "normal"
# 나머지: 높을수록 위험
if value >= warning_max: return "danger"
if value >= normal_max:  return "warning"
return "normal"
```

## 5. AI 이상탐지 (process_gas_data 내부, 룰과 병행)

```
co/h2s/co2 각 deque(maxlen=30) append
  │ len >= 30 ?
  ▼
change point 게이트: _detect_change_point(window)  ← 패턴 변화 없으면 추론 skip (비용 절감)
  │ 변화 감지 시
  ▼
IF 추론: _build_multi_feature_row(co,h2s,co2 window, arima) → model.predict
  │ pred == -1 (이상)?
  ▼
60s rate limit (_gas_last_fired_at) → should_fire
  ├─ push_alarm(...)              실시간 알람 직접 push
  ├─ forward_inference_e2e(...)   ML 결과 + AlarmRecord 비동기 저장
  └─ mark_gas_ai_recent/state     룰 60s mute 마킹 (co/h2s/co2 3종)
```
- **ARIMA 잔차 피처**: 모델 있으면 12피처→15피처. `_arima_models` 모듈 레벨 로드.
- **AI mute**: AI 발화 시 같은 센서 룰 알람 60s 억제. drf `gas_alarm` 이 `is_gas_ai_mute_active(sensor.device_name, gas, level)` 로 읽어 가드 — 키는 **device_name(mac)** 으로 fastapi 와 일치시킴.

## 6. 알람 판정 (gas_alarm.trigger_gas_alarms)

9가스 루프, 각 가스마다 (gas_alarm.py:97~):
```python
if risk == "danger":
    # AI mute 가드 (co/h2s/co2 한정)
    if gas in _AI_GUARDED_GASES and is_gas_ai_mute_active(sensor.device_name, gas, "danger"):
        continue
    # 원자 천이 — 직전 danger 아닐 때만 1회 fire (race-safe)
    if try_transition(state_key, "danger", _CACHE_TTL):   # _CACHE_TTL=60
        fire_danger_alarm_task.delay(sensor_id, gas, value, facility_id, source_label, ...)
elif risk == "warning":
    if get_state(state_key) in ("warning", "danger"): continue   # 이미 발화 중
    # WARNING 은 cache.add(SETNX) 로 첫 도착자만 30s 타이머 시작
```
- **WARNING 30s 지속**: `fire_warning_alarm_task.apply_async(countdown=WARNING_DURATION_SEC)`. 30초 안에 normal 되면 타이머 revoke → 노이즈 억제.
- 알람 생성 자체는 [alerts.md](alerts.md) 의 `create_alarm_and_event` 공유.

## 7. 더미 시뮬레이터 (dummies/gas_dummy.py)

실장비 대신 학습·시연 데이터 생성. 상태머신(RAMP_UP→HOLD→RAMP_DOWN)으로 "정상→사고→회복" 시계열 자기상관 확보 (IF 학습 품질).
```python
SCENARIOS = {
  "co_leak":   {"co": "danger", "co2": "warning", "o2": "warning"},
  "h2s_leak":  {"h2s": "danger", "o2": "warning", "so2": "warning"},
  "fire":      {"lel": "danger", "co": "warning", "co2": "danger", "o2": "danger", "voc": "warning"},
  "chemical_spill": {...}, "o2_depletion": {"o2": "danger"}, "sensor_fault": {},  # 전 가스 0
}
```
- `anomaly_type` 페이로드 동봉 → DB `GasData.is_anomaly/anomaly_type` 로 학습·평가셋 추출.
- `mixed` 모드: 정상 90% + 가중치 시나리오 10%.

## 8. 리뷰 시 주의 (함정)

1. **임계치 이원화** (§4) — fastapi/drf 양쪽 동시 수정. 최우선 주의.
2. **`None` vs `0`**: O2 는 0%(산소 결핍)가 유효 측정값. None(미측정)만 결측 처리. 센서 데이터 전반 원칙.
3. **LEL 제외**: 9종 운영 측정에 LEL 없음 (임계치 미정의). `raw_payload` 에만 보관, 상태 판정·DB 컬럼 제외.
4. **try_transition ttl**: gas_alarm 은 `_CACHE_TTL=60` 으로 호출 (기본 3600 아님) — 재알림 쿨다운과 정렬. [alerts.md](alerts.md) §8.3 함정 참조.
5. **AI mute 키 일치**: drf 가 `sensor.device_name`(mac), fastapi 가 `payload.device_id`(mac) — 둘이 같은 mac 이어야 가드 동작. PK 쓰면 mismatch.

## 9. 관련 문서
- 알람 생성 공유 흐름: [alerts.md](alerts.md)
- AI 추론 엔진 상세: [ai-ml.md](ai-ml.md)
- WS 전달: [websocket.md](websocket.md)
