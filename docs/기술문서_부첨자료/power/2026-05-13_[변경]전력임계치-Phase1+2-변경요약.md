# 전력 임계치 Phase 1+2 — 변경 요약

> **요약 한 줄**: 전력 알람을 "W 단일축·절대값(2200/2860W)" → "W·A·V 3축·채널별 정격 % 기반"으로 전환하고, 채널-설비 매핑을 DB(`PowerDevice.channel_meta`)로 이관해 운영자가 어드민에서 직접 관리하게 한다.

**브랜치**: `feature/power_refactory` (Alarm Phase 1+2 후속) · **커밋**: 6개 (C1~C6) · **머지 PR 단위**: 단일 PR · **상세 plan**: [skill/plan/power-threshold-roadmap.md](../../../skill/plan/power-threshold-roadmap.md) §1~2단계 (gitignore 영역)

---

## 왜 이 작업을 했나

### 기존 동작의 한계

| 항목 | 기존 동작 | 한계 |
|---|---|---|
| 평가 축 | W(전력) 단일 | 전류·전압 이상 미감지 |
| 임계치 기준 | 절대값 (2200W / 2860W) | 정격이 다른 설비에 동일 기준 → 오탐·미탐 |
| 저전압 위험 | 감지 불가 | V² ∝ 토크, 저전압이 모터 과부하 유발하지만 알람 없음 |
| 채널 라벨 | 코드 하드코딩 ([_CHANNEL_NAME](../../../drf-server/apps/monitoring/services/power_alarm.py), CHANNEL_TO_DEVICE) | 사이트별 다른 설비 매핑을 코드 수정 없이 못 바꿈 |
| 채널 정보 출처 | 8개 채널만 라벨, 9-16은 "CH9~CH16" | 도메인 입력이 부재한 상태로 운영 어려움 |

### 코드 검토에서 확인한 결함 5가지

| # | 문제 | 위치 | 영향 |
|---|---|---|---|
| 1 | `evaluate_power_risk(watt)`이 channel/device 인자 없음 | `threshold_service.py:134` | 채널별 정격 환산 불가 |
| 2 | 전류·전압 평가 함수 부재 | 동일 | 3축 위험도 산출 불가 |
| 3 | `power_alarm._evaluate`이 watt 절대값만 평가 | `power_alarm.py:70` | W 외 축 알람 미발화 |
| 4 | `_CHANNEL_NAME` 하드코딩 8개 | `power_alarm.py:34-43` | 운영자가 라벨 수정 못 함 |
| 5 | `CHANNEL_TO_DEVICE` 하드코딩 16개 | `power_service.py:21-38` | FastAPI 페이로드 라벨도 코드 의존 |

### 도메인 입력 부재라는 현실

본 작업은 **도메인 임계치 근거(설비 명판·정격)가 부재한 PoC 단계**에서 시작. 따라서:
- 채널-설비 매핑은 운영자가 어드민에서 수정 가능한 구조로 마련
- 정격값은 산업 표준 추정값으로 시드하고 운영자가 명판 확인 후 정정
- 정격값 없는 채널은 graceful NORMAL (기존 절대값 fallback)

### 인프라 제약 (변경 없음)

- **Alarm Phase 1 계약 유지**: `try_transition` 시그니처, `alarm:power:state:*` 키 네이밍, Celery `default` 큐, `_push_to_ws` retry — 모두 불변
- **`power_default` Threshold 미변경**: 기존 절대값 임계치는 fallback으로 보존 (legacy 호환)
- **신규 모델/마이그레이션 최소화**: `PowerDevice.channel_meta` JSONField는 이미 존재 — 데이터 시드만으로 해결

---

## 단계별 변경 (C1~C6)

각 단계는 단독 커밋이라 문제 발생 시 단계 단위 롤백 가능.

### C1 — `channel_meta` 16채널 추정값 시드 + 어드민 노출

**무엇**
- 신규 [drf-server/apps/facilities/migrations/0017_seed_power_channel_meta.py](../../../drf-server/apps/facilities/migrations/0017_seed_power_channel_meta.py) — RunPython 데이터 마이그레이션
  - 16채널 `{name, rated_w, rated_a, rated_v}` 추정값 시드 (압연기 7.5kW, 송풍기 3.7kW, ... 조명/제어 1kW @220V, 예비 등)
  - **per-key merge**: 이미 운영자가 입력한 키는 보존, 누락 채널만 채움 (운영 DB 보호)
  - revert는 no-op (운영자 정정값과 시드값 구분 불가)
- 수정 [drf-server/apps/facilities/admin.py:59-93](../../../drf-server/apps/facilities/admin.py#L59-L93) — `PowerDeviceAdmin.fields`에 `channel_meta` 노출

**왜**
- `PowerDevice` 한 대의 16채널이 서로 다른 설비라 디바이스 단위 정격은 부적합. JSON 채널 단위 저장이 도메인과 일치
- JSONField는 이미 존재 → 마이그레이션 0건, 데이터 시드만으로 완성
- 운영자가 어드민에서 라벨·정격을 직접 정정 (도메인 입력 부재 시기를 자연스럽게 흡수)

**검증**
```bash
python manage.py migrate facilities 0017
python manage.py shell -c "
from apps.facilities.models import PowerDevice
d = PowerDevice.objects.first()
print(d.channel_meta['1'])
# {'name': '압연기', 'rated_w': 7500, 'rated_a': 30, 'rated_v': 380}
"
```

---

### C2 — Threshold 그룹 `power_facility_default` 시드

**무엇**
- 신규 [drf-server/apps/facilities/migrations/0018_seed_power_facility_default.py](../../../drf-server/apps/facilities/migrations/0018_seed_power_facility_default.py)
  - `ThresholdGroup("power_facility_default")` + 3 Threshold row
  - `power_w`: warning 80%, danger 100% (단방향)
  - `current`: warning 80%, danger 100% (단방향)
  - `voltage`: warning ±5%, danger ±10% (**양방향** — 저전압도 위험)

**왜**
- 정격 % 기반 임계치의 DB 진실 공급원
- 가스의 `gas_legal ↔ gas_facility_default` 우선순위 패턴 재사용 → 일관성
- `power_default.power_w` (2200/2860W) 미변경 — 정격 정보 부재 시 절대값 fallback 보존

---

### C3 — 평가 함수 W·A·V 3축 확장

**무엇**
- 수정 [drf-server/apps/facilities/services/threshold_service.py](../../../drf-server/apps/facilities/services/threshold_service.py) L134~ 신규 5개 함수
  - `_get_channel_rated(device_id, channel, key)` — channel_meta에서 정격 조회. device_id 단위 60초 캐시
  - `_evaluate_with_rated(value, rated, threshold, bidirectional=False)` — 정격 % 환산, `>=` 시맨틱(가스와 일관)
  - `_legacy_power_w_absolute(watt)` — `power_default` 절대값 fallback (`>` 시맨틱, 기존 회귀 방지)
  - `evaluate_power_risk(watt, channel=None, device_id=None)` — 정격 % path + legacy fallback. **단일 exit point** (Phase 4 IF hook)
  - `evaluate_current_risk(amp, channel, device_id)` — 단방향
  - `evaluate_voltage_risk(volt, channel, device_id)` — 양방향(`evaluate_gas_risk`의 O2 분기 패턴 재사용)

**왜**
- 정격 % 환산이 필요한 시점에 한 곳에서 조회·캐싱 (`_get_channel_rated`)
- `>=` 시맨틱은 가스와 동일 (가스 80% boundary == WARNING 패턴)
- 후방 호환: `evaluate_power_risk(watt)` 무인자 호출 시 기존 절대값 path로 동작 → 기존 6개 테스트 그대로 통과
- 단일 exit point는 향후 IF 결합 시 dict 반환으로 확장 가능한 구조 (Phase 4 hook)

**검증**
```bash
.venv/bin/python -m pytest apps/facilities/tests/test_evaluate_power_axes.py -v
# 8 passed — W·A·V 경계값 + graceful + 후방 호환
```

---

### C4 — `power_alarm.py` 3축 통합 (max-of-3 aggregate)

**무엇**
- 수정 [drf-server/apps/monitoring/services/power_alarm.py](../../../drf-server/apps/monitoring/services/power_alarm.py) — 전체 재구성
  - `_CHANNEL_NAME` 하드코딩 삭제 → `_channel_label(device, channel)`이 `device.channel_meta[ch]["name"]` 조회, 미지정 시 `"CH{n}"` fallback
  - 신규 헬퍼: `_axis_risk_key`, `_aggregate_risk`, `_max_risk`, `_EVALUATORS` 매핑
  - `trigger_power_alarms`:
    1. `axis = objs[0].data_type` → 해당 축 평가 함수 호출
    2. 축별 위험도 캐시 `alarm:power:risk:{dev}:{ch}:{axis}` 갱신 (TTL 300s)
    3. `cache.get_many`로 3축 위험도 한 번에 조회
    4. `aggregate = max(W_risk, A_risk, V_risk)` 산출
    5. `try_transition(state_key, aggregate, ttl)` — **Phase 1 계약 그대로**

**왜**
- 단일 dedupe 경계 유지: `state_key="alarm:power:state:{dev}:{ch}"` 변경 금지 (Phase 1 계약). 3축은 호출 *이전*에 max로 통합
- 새 캐시 `alarm:power:risk:*`는 sibling 네임스페이스 (Phase 1 자리 침범 없음)
- `WARNING_DURATION_SEC=3` Celery apply_async 패턴·`fire_*_task.delay()` 시그니처·`_revoke`·`cache.add` SETNX race 차단 — 모두 불변
- 채널 라벨도 함께 DB 기반으로 이관 → 운영자 라벨 수정이 알람 메시지에 반영

**Phase 1 계약 검증** (모두 통과)
- `try_transition` 시그니처 불변 ✅
- `alarm:power:state:{device_id}:{channel}` 네이밍 불변 ✅
- `alarm:power:task:{device_id}:{channel}` 네이밍 불변 ✅
- Celery `default` 큐 유지 ✅
- `_push_to_ws` retry 정책 미터치 ✅

**검증**
```bash
.venv/bin/python -m pytest apps/monitoring/tests/test_power_alarm_axis_combine.py -v
# 6 passed — 축별 캐시 격리 / W WARNING → A DANGER 중복 차단 / 저전압 단독 DANGER / 회복 시 clear
```

---

### C5 — FastAPI WS 페이로드 3축 필드 + `channel_meta` 캐시

**무엇**
- 신규 [fastapi-server/power/services/channel_meta_cache.py](../../../fastapi-server/power/services/channel_meta_cache.py)
  - 5분 주기로 DRF `GET /api/monitoring/power/channel-meta/` 호출 → 모듈 캐시 갱신
  - `get_channel_entry(device_id, channel)` — 라벨·정격 조회 헬퍼
- 신규 [drf-server/apps/monitoring/views/power_data.py](../../../drf-server/apps/monitoring/views/power_data.py) `PowerChannelMetaView`
  - 활성 PowerDevice의 `channel_meta` JSON 노출 (AllowAny, `PowerThresholdView`와 동일 정책)
- 수정 [fastapi-server/power/services/power_service.py](../../../fastapi-server/power/services/power_service.py)
  - `CHANNEL_TO_DEVICE` 하드코딩 삭제
  - `_eval_axis_pct(value, rated, axis)` — 정격 % 환산 표시용 (DRF와 동일 `>=` 시맨틱)
  - `build_equipment()` 페이로드에 `power_risk`/`current_risk`/`voltage_risk` + `risk_level = max(3축)` 추가
  - 정격 정보 없는 채널은 `POWER_THRESHOLDS` 절대값 watt fallback (graceful)
- 수정 [fastapi-server/app.py](../../../fastapi-server/app.py) lifespan에 `channel_meta_refresh_loop` 추가

**왜**
- 채널 라벨은 DRF가 단일 진실 공급원 → fastapi는 표시용으로 fetch
- 임계치 % 값(80/100/95/105/90/110)이 fastapi에 박힌 것은 표시용이며 향후 별도 후속에서 DRF endpoint로 동기화 가능 — 본 PR 범위에서는 명시적 코드 중복 수용
- 운영자가 어드민에서 라벨 변경 → 최대 5분 후 대시보드 반영 (TTL)

**검증** (build_equipment 직접 호출)
```python
update_power_state('watt',    {1: 6200,  15: 200})
update_power_state('current', {1: 32,    15: 4})
update_power_state('voltage', {1: 340,   15: 220})
eq, _ = build_equipment()
# ch1 (압연기):
#   power_risk=warning (82.6%), current_risk=danger (106%), voltage_risk=danger (89%)
#   risk_level=danger (max)
# ch15 (조명/제어):
#   power_risk=normal (20%), current_risk=warning (80%), voltage_risk=normal (100%)
#   risk_level=warning
```

---

### C6 — 테스트

**무엇**
- 신규 [drf-server/apps/facilities/tests/test_evaluate_power_axes.py](../../../drf-server/apps/facilities/tests/test_evaluate_power_axes.py) — 8 케이스
  - W·A·V 경계값 (79/80/81%, 99/100/101%, 양방향 89/90/91%, 109/110/111%)
  - graceful 경로 (정격 미입력, 임계치 그룹 부재)
  - 후방 호환 (`evaluate_power_risk(watt)` 무인자)
- 신규 [drf-server/apps/monitoring/tests/test_power_alarm_axis_combine.py](../../../drf-server/apps/monitoring/tests/test_power_alarm_axis_combine.py) — 6 케이스
  - 축별 캐시 격리 (W·A·V 키 독립)
  - W WARNING → A DANGER 진입 시 fire 정확히 1회씩 (중복 차단)
  - 저전압 단독 DANGER (이전엔 못 잡던 위험)
  - 회복 시 `fire_power_clear` 1회 + state 정리
  - 미등록 data_type early return
  - 라벨 없는 채널 `"CH{n}"` fallback

**전체 회귀** (Phase 1 회귀 포함):
```bash
.venv/bin/python -m pytest apps/monitoring/tests/ apps/facilities/tests/ -v
# 26 passed — 기존 12 + 신규 14
```

---

## E2E 검증 (Docker compose)

- DRF `/api/monitoring/power/channel-meta/` 응답 검증 → 1 device, 16 channels (압연기/송풍기/... 메인 전력반/... 조명/제어/예비)
- FastAPI lifespan startup 로그: `[channel_meta_cache] refreshed devices=1 channels=16`
- 저전압 시나리오 (ch1 voltage 340V = 89% of 380V 정격) → 알람 DB row DANGER 1건, `_push_to_ws` 즉시 발화
- 전류 초과 시나리오 (ch1 current 32A = 106% of 30A 정격) → 동일 채널 aggregate DANGER 유지, 중복 fire 차단 (Phase 1 dedupe)
- 직접 `trigger_power_alarms`로 ch15 voltage 380V 호출 → fire 인자 `(device_id=1, channel=15, value=380, facility_id=1, label='조명/제어')` 정확

---

## 알려진 제약사항 / 후속 작업

| # | 항목 | 본 PR | 후속 |
|---|---|---|---|
| 1 | 알람 메시지에 축 정보 미포함 | 메시지 "{value}W" 표기는 W 알람 외엔 단위 부정확 | Phase 5에서 `fire_power_*_task` 시그니처에 `axis` 추가 검토 |
| 2 | `channel_meta` 캐시 TTL 5분 (fastapi) | 어드민 수정 후 5분 지연 | 무효화 endpoint 또는 PowerDevice post_save signal 추가 검토 |
| 3 | `PowerThresholdView` chart_max | `power_default` 절대값 그대로 → 차트 Y축은 3500W | `power_facility_default` 기반으로 정격 % 환산 차트 별도 작업 |
| 4 | 지속시간 카운터 / 히스테리시스 | 미적용 (즉시 발화 유지) | Phase 5 — IF anomaly 분포 보고 결정 |
| 5 | 더미 시나리오 5종 (overload/voltage_drop/spike/phase_loss/degradation) | 미적용 | Phase 3 별도 PR |
| 6 | IF 이상탐지 결합 | hook 자리만 (단일 exit point) | Phase 4 별도 plan (`apps/ml/`) |

---

## 단계 간 의존성

```
C1 (channel_meta 시드) ─┐
C2 (Threshold 시드)    ─┴─→ C3 (eval 함수) ─→ C4 (alarm 라우터) ─→ C5 (WS 페이로드) ─→ C6 (테스트)
```

C1·C2 병렬 가능. C3 이후 순차.

---

## 변경 파일 요약

| 영역 | 파일 | 변경 유형 |
|---|---|---|
| 마이그레이션 | `facilities/migrations/0017_seed_power_channel_meta.py` | 신규 |
| 마이그레이션 | `facilities/migrations/0018_seed_power_facility_default.py` | 신규 |
| 어드민 | `facilities/admin.py` | `channel_meta` fields 노출 |
| 평가 함수 | `facilities/services/threshold_service.py` | 5개 함수 신규/확장 |
| 알람 라우터 | `monitoring/services/power_alarm.py` | 전체 재구성 (3축 통합) |
| API | `monitoring/views/power_data.py` | `PowerChannelMetaView` 신규 |
| URL | `monitoring/urls.py` | `/api/monitoring/power/channel-meta/` 추가 |
| FastAPI | `fastapi-server/power/services/channel_meta_cache.py` | 신규 |
| FastAPI | `fastapi-server/power/services/power_service.py` | 3축 페이로드 + DB 라벨 |
| FastAPI | `fastapi-server/app.py` | lifespan에 refresh loop 추가 |
| 테스트 | `facilities/tests/test_evaluate_power_axes.py` | 신규 (8) |
| 테스트 | `monitoring/tests/test_power_alarm_axis_combine.py` | 신규 (6) |
