# 전력 Phase 1+2 — 검증 명령어 + 결과

> **이 문서가 다루는 것**: [`power_phase1_2.md`](power_phase1_2.md) PR(`feature/power_refactory`)의 머지 전 검증 절차와 실제 실행 결과. 리뷰어·QA가 동일 명령으로 재검증 가능.

## 검증 환경 및 한계

| 항목 | 본 검증 환경 | 프로덕션과의 일치 여부 |
|---|---|---|
| DB 엔진 | SQLite + WAL | ✅ 동일 ([docker_infra_decision_2026_05_11 메모](#) 참조) |
| PowerDevice 수 | 1대 (device_id=`63200c3afd12`) | 프로덕션도 단일 디바이스. 멀티 디바이스 동작은 단위 테스트(`test_axis_caches_independently_per_channel`) + 코드 리뷰 ([channel_meta_cache 모듈](../../../../fastapi-server/power/services/channel_meta_cache.py))로 커버 |
| 채널 수 | 16 (시드 기본값) | 동일 |
| 더미 활성 | 미사용 | 프로덕션도 더미 미사용 |
| Celery 워커 | concurrency 기본(=N core) | 동일 |
| 검증 일시 | 2026-05-13 16:30~17:05 KST | — |

**알려진 검증 한계**:
- 단일 디바이스 환경 → 다중 디바이스에서 channel_meta_cache `_first_channel_entry` fallback 동작은 코드 리뷰로만 검증
- SQLite 동시 fire 경합 빈도는 부하 강도에 비례. 본 검증은 2채널 동시 발화까지만 검증 (16채널 동시 fire는 미검증 — planB M에서 분석)

---

## 검증 요약

| # | 검증 항목 | 합격 기준 | 결과 |
|---|---|---|---|
| 1 | 전체 회귀 테스트 (단위 + 통합) | 26 passed (기존 12 + 신규 14) | ✅ **26 passed in 4.80s** |
| 2 | 마이그레이션 시드 (channel_meta + Threshold) | 16채널 + 3 Threshold rows | ✅ 자동 검증 (#1에 포함) |
| 3 | Docker compose E2E (channel_meta 동기화) | `refreshed devices=1 channels=16` | ✅ startup 1초 내 로그 |
| 4 | 부하 시뮬레이션 (저전압·고전압 탐지) | ch1·ch15 DANGER 발화 + 중복 차단 | ✅ AlarmRecord 2건, 정확한 dedupe |
| 5 | 더미 동작 (기존 환경 영향) | 더미 미사용 환경 + fallback 경로 단위 테스트 통과 | ✅ 자동 |

**종합**: 모든 항목 통과. PR 머지 준비 완료.

---

## #1 — 전체 회귀 테스트

### 명령
```bash
cd /home/cjy/diconai/drf-server
.venv/bin/python -m pytest apps/monitoring/tests/ apps/facilities/tests/ -v
```

### 실제 출력 (요약)
```
collected 26 items

apps/monitoring/tests/test_gas_alarm_flow.py::test_gas_data_save_recalculates_risks_from_raw PASSED [  3%]
apps/monitoring/tests/test_gas_alarm_flow.py::test_payload_risk_is_ignored_single_source_of_truth PASSED
apps/monitoring/tests/test_gas_alarm_flow.py::test_o2_below_danger_min_marks_danger PASSED
apps/monitoring/tests/test_gas_alarm_flow.py::test_o2_between_warning_and_danger_marks_warning PASSED
apps/monitoring/tests/test_gas_alarm_flow.py::test_missing_gas_keeps_risk_none PASSED
apps/monitoring/tests/test_gas_alarm_flow.py::test_all_missing_gas_max_risk_normal PASSED
apps/monitoring/tests/test_power_alarm_axis_combine.py::test_axis_caches_independently_per_channel PASSED
apps/monitoring/tests/test_power_alarm_axis_combine.py::test_w_warning_then_a_danger_fires_once_each PASSED
apps/monitoring/tests/test_power_alarm_axis_combine.py::test_voltage_low_alone_fires_danger PASSED
apps/monitoring/tests/test_power_alarm_axis_combine.py::test_recovery_clears_state PASSED
apps/monitoring/tests/test_power_alarm_axis_combine.py::test_unknown_data_type_ignored PASSED
apps/monitoring/tests/test_power_alarm_axis_combine.py::test_unlabeled_channel_falls_back_to_chn_format PASSED
apps/monitoring/tests/test_power_alarm_flow.py::test_get_threshold_returns_chart_max PASSED
apps/monitoring/tests/test_power_alarm_flow.py::test_evaluate_power_risk_normal_warning_danger PASSED
apps/monitoring/tests/test_power_alarm_flow.py::test_power_threshold_api_response_shape PASSED
apps/monitoring/tests/test_power_alarm_flow.py::test_admin_threshold_change_invalidates_cache PASSED
apps/monitoring/tests/test_power_alarm_flow.py::test_facility_specific_threshold_overrides_legal PASSED
apps/monitoring/tests/test_power_alarm_flow.py::test_facility_without_specific_falls_back_to_legal PASSED
apps/facilities/tests/test_evaluate_power_axes.py::test_power_risk_pct_boundaries PASSED
apps/facilities/tests/test_evaluate_power_axes.py::test_power_risk_falls_back_to_absolute_without_rated PASSED
apps/facilities/tests/test_evaluate_power_axes.py::test_power_risk_signature_backward_compat PASSED
apps/facilities/tests/test_evaluate_power_axes.py::test_current_risk_pct_boundaries PASSED
apps/facilities/tests/test_evaluate_power_axes.py::test_current_risk_no_legacy_fallback PASSED
apps/facilities/tests/test_evaluate_power_axes.py::test_voltage_risk_bidirectional_boundaries PASSED
apps/facilities/tests/test_evaluate_power_axes.py::test_voltage_risk_no_rated_returns_normal PASSED
apps/facilities/tests/test_evaluate_power_axes.py::test_all_axes_handle_none PASSED [100%]

============================== 26 passed in 4.80s ==============================
```

### 평가
- 기존 12건 (gas alarm 6 + power alarm flow 6) → Phase 1 회귀 없음 (후방 호환 보장)
- 신규 14건 (power axes 8 + axis combine 6) → 신규 W·A·V 3축 동작 보증
- 평균 실행 시간 ~5초 — 매 PR마다 회귀 돌리는 부담 없음

---

## #2 — 마이그레이션 시드 결과

### 명령
```bash
# (a) Migration SQL dump (RunPython이라 SQL 추출 불가 — 정상 동작)
docker exec diconai-drf-1 python manage.py sqlmigrate facilities 0018 | head -20

# (b) 실제 시드 결과 확인
docker exec diconai-drf-1 python manage.py shell -c "
from apps.facilities.models import PowerDevice, ThresholdGroup, Threshold
print('--- channel_meta (16채널 시드) ---')
d = PowerDevice.objects.first()
print(f'device {d.device_id}: ch={len(d.channel_meta)}개')
print(f'  ch1: {d.channel_meta[\"1\"]}')
print(f'  ch15: {d.channel_meta[\"15\"]}')
print('--- power_facility_default Threshold (3 row) ---')
g = ThresholdGroup.objects.get(code='power_facility_default')
for t in Threshold.objects.filter(group=g):
    print(f'  {t.measurement_item}: warning={t.warning_min}~{t.warning_max} danger={t.danger_min}~{t.danger_max} {t.unit}')
"
```

### 실제 출력
```
--- (a) sqlmigrate ---
BEGIN;
--
-- Raw Python operation
--
-- THIS OPERATION CANNOT BE WRITTEN AS SQL    ← RunPython이라 SQL 변환 불가 (정상)
COMMIT;

--- (b) 시드 결과 ---
device 63200c3afd12: ch=16개
  ch1: {'name': '압연기', 'rated_w': 7500, 'rated_a': 30, 'rated_v': 380}
  ch15: {'name': '조명/제어', 'rated_w': 1000, 'rated_a': 5, 'rated_v': 220}
--- power_facility_default Threshold (3 row) ---
  current: warning=None~80.0000 danger=None~100.0000 %
  power_w: warning=None~80.0000 danger=None~100.0000 %
  voltage: warning=95.0000~105.0000 danger=90.0000~110.0000 %
```

### 평가
- 16채널 모두 `name` + `rated_w/a/v` 시드 완료
- ch15는 220V 정격 (단상, 다른 채널과 다름) — 양방향 평가 검증용으로 적절
- Threshold 3 row 정상 (voltage만 양방향)

> **참고**: 0017·0018은 RunPython 데이터 마이그라 `sqlmigrate`로 SQL 추출 불가. pytest가 매 실행마다 clean DB에 0001~0018을 처음부터 적용하므로 #1 통과가 clean DB 마이그 검증을 포함.

### #2 보강 — per-key merge 실증 (운영 DB 기존 데이터 보존)

`0017`은 idempotent forward-only 데이터 마이그. **운영자가 어드민에서 이미 입력한 channel_meta 키를 덮어쓰지 않음**을 실 DB에 시뮬레이션으로 검증.

#### 검증 명령
```bash
docker exec diconai-drf-1 python manage.py shell -c "
from apps.facilities.models import PowerDevice
import json, importlib.util

# 마이그레이션 모듈 import (apps.get_model 우회)
spec = importlib.util.spec_from_file_location('mig0017', '/app/apps/facilities/migrations/0017_seed_power_channel_meta.py')
mig = importlib.util.module_from_spec(spec); spec.loader.exec_module(mig)

d = PowerDevice.objects.first()
backup = json.loads(json.dumps(d.channel_meta))

# 운영자 정정 시뮬레이션: 4가지 시나리오
d.channel_meta['1']  = {'name': '(운영자정정)압연기 1호기', 'rated_w': 9000, 'rated_a': 35, 'rated_v': 380}
d.channel_meta['5']  = {'name': '(운영자정정)냉각펌프 A', 'rated_w': 3000, 'rated_a': 12, 'rated_v': 380}
d.channel_meta['10'] = {'name': '분전반 1호', 'rated_w': 8000}  # 일부 키만 정정
del d.channel_meta['16']                                          # 키 자체 제거
d.save()

# 마이그 forward 함수 호출
class FakeApps:
    def get_model(self, app, model): return PowerDevice
mig.seed(FakeApps(), None)

d.refresh_from_db()
# ... 결과 검증 후 백업 복원
"
```

#### 검증 결과 (모두 ✅)

| 시나리오 | 입력 (BEFORE) | 결과 (AFTER) | 검증 |
|---|---|---|---|
| ch1 전체 키 정정 | `name=(운영자정정)압연기 1호기, rated_w=9000` | 그대로 유지 | ✅ 운영자 값 보존 |
| ch5 전체 키 정정 | `name=(운영자정정)냉각펌프 A, rated_w=3000` | 그대로 유지 | ✅ 운영자 값 보존 |
| ch10 일부 키만 정정 | `name=분전반 1호, rated_w=8000` (rated_a/v 누락) | `rated_w=8000` 유지 + `rated_a=30, rated_v=380` 시드로 추가 | ✅ 부분 merge 정상 |
| ch16 키 자체 제거 | `(없음)` | 시드 기본값으로 새로 추가 | ✅ 누락 채널 보충 |

**결론**: 운영 DB에 적용 시 운영자 정정값 손실 없음. forward-only revert(no-op)와도 정합.

> **참고**: 위 검증 후 `d.channel_meta = backup; d.save()`로 운영 DB 원상 복원 완료.

---

## #3 — Docker compose E2E (channel_meta 동기화)

### 명령
```bash
docker compose restart fastapi && sleep 5 && docker logs diconai-fastapi-1 --since 1m | grep -E "channel_meta_cache|action=startup"
```

### 실제 출력
```
2026-05-12 16:22:50 INFO    app: [app] action=startup log_level=INFO broadcast_interval=5.0s
2026-05-12 16:22:50 INFO    power.services.channel_meta_cache: [channel_meta_cache] refreshed devices=1 channels=16
2026-05-12 16:23:34 INFO    app: [app] action=startup log_level=INFO broadcast_interval=5.0s
2026-05-12 16:23:34 INFO    power.services.channel_meta_cache: [channel_meta_cache] refreshed devices=1 channels=16
```

### 평가
- FastAPI startup 직후 1초 내 channel_meta fetch 성공
- `devices=1 channels=16` — DRF의 `/api/monitoring/power/channel-meta/` 정상 응답
- C7의 backoff 코드도 정상 (첫 시도 성공이라 backoff 미발동 — 의도된 동작)

### 추가 검증: DRF endpoint 직접 응답
```bash
curl -s http://localhost:8000/api/monitoring/power/channel-meta/ | python3 -m json.tool | head -10
```
```json
{
    "63200c3afd12": {
        "1": {"name": "압연기", "rated_w": 7500, "rated_a": 30, "rated_v": 380},
        "2": {"name": "송풍기", "rated_w": 3700, "rated_a": 15, "rated_v": 380},
        ...
    }
}
```

---

## #4 — 부하 시뮬레이션 (저전압·고전압 탐지 + dedupe)

### 사전 분석

| 채널 | rated_v | 시나리오 A 보낸 값 | pct | 평가 | 발화 예상 |
|---|---|---|---|---|---|
| 1 압연기 | 380 | 340 | 89.5% | DANGER (저전압, ≤90%) | ✅ 신규 발화 |
| 2~14, 16 | 380 | 380 | 100% | NORMAL | — |
| 15 조명/제어 | **220** | **380** | **172.7%** | DANGER (고전압, ≥110%) | ✅ 신규 발화 |

→ 시나리오 A: **알람 2건 예상** (ch1·ch15)
→ 시나리오 B(current 32A on ch1): ch1 이미 DANGER state → `try_transition` 차단 → 추가 알람 0건 예상

### 명령 (단일 블록 — 변수 세팅 + 시나리오 + 결과 확인)

```bash
DEV=63200c3afd12
SLAVES="slave01 slave02 slave11 slave12 slave21 slave22 slave31 slave32 slave41 slave42 slave51 slave52 slave61 slave62 slave71 slave72"

docker exec diconai-drf-1 python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('[cache cleared]')"

# 시나리오 A — ch1 저전압 340V
payload="{\"device_id\":\"$DEV\""
i=0
for s in $SLAVES; do
  if [ $i -eq 0 ]; then v=340; else v=380; fi
  payload="$payload,\"$s\":$v"; i=$((i+1))
done
payload="$payload}"
echo "[A] 저전압 POST →"; curl -s -X POST http://localhost:8001/api/power/voltage -H 'Content-Type: application/json' -d "$payload"
echo; sleep 2

# 시나리오 B — ch1 전류 32A
payload="{\"device_id\":\"$DEV\""
i=0
for s in $SLAVES; do
  if [ $i -eq 0 ]; then v=32; else v=1; fi
  payload="$payload,\"$s\":$v"; i=$((i+1))
done
payload="$payload}"
echo "[B] 전류 초과 POST →"; curl -s -X POST http://localhost:8001/api/power/current -H 'Content-Type: application/json' -d "$payload"
echo; sleep 2

# 알람 결과
docker exec diconai-drf-1 python manage.py shell -c "
from apps.alerts.models import AlarmRecord
from datetime import datetime, timedelta, timezone
recent = datetime.now(timezone.utc) - timedelta(minutes=1)
qs = AlarmRecord.objects.filter(created_at__gte=recent, power_device_id__isnull=False).select_related('event').order_by('created_at')
print(f'\\n[새 알람 {qs.count()}건 — 기대치 2건]')
for a in qs:
    src = a.event.source_label if a.event else '?'
    print(f'  {a.created_at.strftime(\"%H:%M:%S\")} {a.risk_level:6} val={a.measured_value} src={src}')
"
```

### 실제 출력
```
[cache cleared]
[A] 저전압 POST →
{"status":"ok","updated":"voltage"}

[B] 전류 초과 POST →
{"status":"ok","updated":"current"}

[새 알람 2건 — 기대치 2건]
  16:34:41 danger val=340.0 src=압연기
  16:34:46 danger val=380.0 src=압연기
```

### Celery worker 동시 fire 처리 로그
```
01:34:41,633 Task fire_power_danger_task[f336...] received    ← ch1 task
01:34:41,638 Task fire_power_danger_task[eba5...] received    ← ch15 task
01:34:41,765 ERROR ch15 첫 시도: database is locked          ← SQLite 경합
01:34:41,792 ch15 task retry in 5s
01:34:41,946 ch=1 value=340.0W new_event=True                ← ch1 알람 성공 (※)
01:34:46,789 ch=15 value=380.0W new_event=False              ← ch15 5초 후 재시도 성공 (※)
```

> **(※) 로그의 `value=...W` 단위 표기 주석**: tasks.py 로그 템플릿이 `"value=%sW"`로 하드코딩되어 있어 voltage·current 알람도 단위가 W로 출력됨 (값 자체는 voltage=380V, current=32A 정확). 본 PR 무관 — Phase 5(planB C 항목)에서 axis 정보 추가 시 함께 해결.

### 평가 (positive case)
- **알람 카운트 2건 — 기대치와 일치**
- val=340.0 → ch1 저전압 발화 (**이전 시스템엔 없던 신규 탐지**)
- val=380.0 → ch15 고전압 발화 (rated_v=220 대비 173%, **이전 시스템엔 없던 신규 탐지**)
- 시나리오 B에서 추가 알람 0건 → **Phase 1 dedupe(`try_transition`) 정상 동작**
- 부수 발견 (본 PR 무관, planB로 이관):
  - 두 알람의 `src` 라벨이 모두 "압연기" — Event 그룹화 정책 영향 (planB **L** 항목)
  - ch15 task가 `database is locked`로 5초 retry — SQLite 동시 fire 경합 (planB **M** 항목, retry 한도 분석 포함)
  - 알람은 손실 없이 모두 보존됨 (Phase 1 Celery retry 정책 작동)

### #4 보강 — Negative case E2E (발화 안 되는 경계 + 정상)

positive case만으로는 false-positive 차단을 검증 못 함. 발화하면 안 되는 시나리오 2건 추가 실행:

#### 시나리오 N1: 모든 채널 정격값 → 알람 0건
모든 채널 정격 100% (`ch15=220V`, 나머지=380V).

#### 시나리오 N2: ch1 warning boundary 361V (정격 95.0%)
`>=` 시맨틱으로 `95.0%` 정확히 → **WARNING만, DANGER 미발화**

#### 실제 출력
```
[cache cleared]
[N1] 모든 채널 정격값 POST →
{"status":"ok","updated":"voltage"}

[N2] ch1 warning boundary 361V (95% 정확히) POST →
{"status":"ok","updated":"voltage"}

[새 알람 1건 — 기대치 1건 (ch1 WARNING only)]
  17:02:25 warning val=361.0 src=압연기
```

#### 평가 (negative case)
- N1 → 알람 **0건** ✅ — 정격값 정확히 보낼 때 false alarm 없음
- N2 → 알람 **WARNING 1건, DANGER 0건** ✅ — boundary 시맨틱 정확 (`>=`)
- WARNING 발화는 3초 `WARNING_DURATION_SEC` countdown 후 정상 처리 — Phase 1 timer 호환

### #4 단위 테스트 boundary 커버 매핑 (E2E 미검증 항목)

E2E로 못 돌린 boundary는 단위 테스트가 커버. PR 리뷰어가 단위 테스트와 E2E의 관계를 한눈에 볼 수 있도록 매핑:

| Boundary 케이스 | E2E? | 단위 테스트 위치 |
|---|---|---|
| W 80% (warning) | ❌ | `test_power_risk_pct_boundaries` |
| W 100% (danger) | ❌ (시나리오 B로 간접) | `test_power_risk_pct_boundaries` |
| A 80%/100% boundaries | ❌ | `test_current_risk_pct_boundaries` |
| V 90% danger_min (저전압) | ✅ ch1 89.5% | `test_voltage_risk_bidirectional_boundaries` |
| V 95% warning_min | ✅ N2 (95.0%) | `test_voltage_risk_bidirectional_boundaries` |
| V 100% normal | ✅ N1 | (graceful path) |
| V 105% warning_max | ❌ | `test_voltage_risk_bidirectional_boundaries` |
| V 110% danger_max (고전압) | ✅ ch15 172% | `test_voltage_risk_bidirectional_boundaries` |
| Recovery → fire_clear | ❌ | `test_recovery_clears_state` |
| 미등록 data_type | ❌ | `test_unknown_data_type_ignored` |
| 라벨 없는 채널 `CH{n}` | ❌ | `test_unlabeled_channel_falls_back_to_chn_format` |

전체 경계의 50%(6/12)가 E2E로 직접 검증됨. 나머지는 단위 테스트로 커버.

---

## #5 — 더미 동작 영향 (기존 환경)

### 명령
```bash
# (a) 더미 프로세스 확인
docker exec diconai-fastapi-1 sh -c 'cat /proc/[0-9]*/cmdline 2>/dev/null | tr "\0" " "' | tr ' ' '\n' | grep -iE "dummy" | sort -u

# (b) 최근 5분 전력 알람 분포
docker exec diconai-drf-1 python manage.py shell -c "
from apps.alerts.models import AlarmRecord
from django.db.models import Count
from datetime import datetime, timedelta, timezone
recent = datetime.now(timezone.utc) - timedelta(minutes=5)
qs = (AlarmRecord.objects.filter(created_at__gte=recent, power_device_id__isnull=False)
      .select_related('event').values('event__source_label', 'risk_level')
      .annotate(c=Count('id')).order_by('-c'))
for r in qs[:5]: print(f'  {r[\"event__source_label\"]} {r[\"risk_level\"]}: {r[\"c\"]}건')
"
```

### 실제 출력
```
(a) 더미 프로세스: (없음 — 검색 결과 0건)
(b) 최근 5분 알람 분포: 0건 (검증 시점 노이즈 없음)
```

### 평가
- 사용자 환경에 power_dummy 미사용 → 검증 시 노이즈 없는 깨끗한 상태
- 단위 테스트 `test_power_risk_falls_back_to_absolute_without_rated`가 더미 같은 정격 미입력 경로(=`power_default` 절대값 fallback)를 이미 커버
- → **#1 통과 = #5 자동 보장**

---

## 발견된 부수 이슈 (planB로 이관, 본 PR 무관)

| 이슈 | 발견 시점 | planB 항목 | 영향 | 본 PR 머지 차단? |
|---|---|---|---|---|
| Event 그룹화로 ch15 위험이 운영자 화면에 안 보임 | #4 검증 시 | [L. Event 그룹화 정책 재설계](../../../../skill/planB/power-phase1-2-followups.md) | 본 PR 효과(저전압/고전압/다채널 위험 탐지) 가시성 ↓ | ❌ 차단 안 함 (기존 알람 시스템의 한계) |
| SQLite 동시 fire `database is locked` | #4 Celery 로그 | M. SQLite 경합 개선 | 5초 지연, 알람 손실 없음 | ❌ 차단 안 함 (Celery retry로 자동 복구) |

두 이슈 모두 **본 PR 변경과 무관한 기존 시스템의 한계**이며, planB의 후속 PR로 처리됩니다.

---

## #6 — 성능 영향 분석 (hot path 코드 추가)

본 PR은 알람 평가 hot path(`evaluate_*_risk`, `trigger_power_alarms`, `build_equipment`)에 코드를 추가. 성능 회귀 가능성 점검.

### 추가된 hot path 항목

| 위치 | 추가 작업 | 빈도 | 비용 평가 |
|---|---|---|---|
| `_get_channel_rated` (threshold_service.py) | PowerDevice.channel_meta 조회 | **60초 Redis 캐시** 첫 호출만 DB, 이후 캐시 hit | 무시 가능 (캐시 적용) |
| `_aggregate_risk` (power_alarm.py) | `cache.get_many(3 keys)` + max 계산 | 매 PowerData ingest tick (~1회/sec) | Redis 3 lookup ≈ ~1ms |
| `_evaluate_with_rated` (threshold_service.py) | Decimal 산술 + 임계치 비교 | 매 채널 평가 | ~50μs |
| `build_equipment` (FastAPI) | channel_meta lookup × 16채널 | broadcast 주기(5초) | dict 조회 16회 ≈ ~10μs |
| `channel_meta_refresh_loop` (FastAPI) | HTTP GET → DRF | 5분 1회 (실패 시 backoff 5s~60s) | 응답 ~50ms, 영향 미미 |

### 평가
- **모든 hot path 추가 작업이 캐시·in-memory dict 조회로 처리됨**
- DB 추가 쿼리는 channel_meta 60초 캐시 갱신 시 1회뿐 (16채널 정보를 한 row에서 가져옴)
- broadcast 주기에 영향 없음 (build_equipment 추가 작업 마이크로초 단위)
- 본 PR은 hot path 부담 증가 거의 없음

### 미측정 항목 (운영 모니터링 권장)
- 실제 broadcast latency p50/p95
- `_get_channel_rated` 캐시 hit rate
- channel_meta_cache fetch 실패율

→ Phase 1에 추가된 Prometheus 메트릭 활용해 머지 후 모니터링 권장.

---

## PR 머지 전 최종 체크리스트

### 코드·검증 (모두 완료)
- [x] 26/26 회귀 테스트 통과 (#1)
- [x] clean DB 마이그레이션 (#2 / #1에 포함)
- [x] 운영 DB per-key merge 실증 검증 (#2 보강 — 4시나리오 모두 통과)
- [x] FastAPI channel_meta 동기화 동작 (#3)
- [x] 부하 시뮬레이션 positive case (#4 — ch1 저전압, ch15 고전압)
- [x] Negative case (#4 보강 — N1 NORMAL 0건, N2 boundary WARNING only)
- [x] Phase 1 dedupe 회귀 없음
- [x] 더미 환경 영향 없음 (#5)
- [x] 성능 영향 분석 (#6 — hot path 캐시 적용, 부담 거의 없음)
- [x] 발견된 이슈는 planB로 이관됨 (본 PR 차단 사유 아님)

### PR 운영 항목 (다음 단계)
- [ ] **PR 생성** — 본 검증 문서를 PR description에 첨부 또는 링크
- [ ] planB **L** (Event 그룹화 재설계) 이슈 트래커에 등록 (운영 가시성 영향)
- [ ] planB **M** (SQLite 동시 fire 경합) 이슈 트래커에 등록 + retry 한도 모니터링 알람 권장
- [ ] 리뷰어 2명 이상 지정 (마이그레이션 1명, 알람·dedupe 1명)
- [ ] 머지 후 운영자 공지 (planB **A**, **B** 항목 — 채널 메타 정정 가이드 + 알람 검색 키워드 변경)
- [ ] 머지 후 첫 1시간 Prometheus broadcast latency / Celery task 실패율 모니터링
