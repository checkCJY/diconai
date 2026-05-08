# B 운영 트랙 + 회귀 점검 Step 2 변경 후 기존 코드 영향 정적 분석

> 작성일: 2026-05-09
> 분석 대상: `eb04045` ~ `d68f56d` (9 commits — 회귀 점검 Step 2 fix + B 운영 트랙 PR-A~H)
> 분석 방식: Explore 에이전트 3개 parallel (grep 정적 분석)
> **결론: 즉시 깨짐 0건. 컨벤션/추적성 권장 사항만 발견.**

---

## 1. Context

`feature/0508_refactory` 브랜치에서 B 운영 트랙 8 PR + 회귀 점검 Step 2 fix 진행 시 다음 변경이 발생:
- **시그니처 변경**: `evaluate_gas_risk(gas, value, facility_id=None)` (PR-G)
- **모델 변경**: `Threshold.facility` FK + UNIQUE 변경 (PR-G), 10개 모델 BaseModel 통일 (PR-B)
- **비동기 전환**: AppLog/IntegrationLog Celery delay() (PR-D)
- **dead code 제거**: `GasTypeChoices.LEL` (PR-E)
- **시드 추가**: AlertPolicy 9종 + DataRetentionPolicy 5종 (PR-C)

회귀 점검 Step 1 ([post_phase4_step1_report.md](post_phase4_step1_report.md))은 Phase 1~4 본체만 점검 — 본 분석은 그 이후 9 commits의 영향 점검.

분석 대상 디렉토리: `drf-server/` + `fastapi-server/` 전체.

---

## 2. 요약 표 (8개 영역)

| # | 영역 | 위험도 | 핵심 발견 |
|---|---|---|---|
| 1 | PR-G `evaluate_gas_risk(facility_id=)` 시그니처 호환성 | 🟢 안전 | 모든 호출처 호환 |
| 2 | PR-G `Threshold.facility` FK + UNIQUE 변경 | 🟢 안전 | 시드/마이그/admin 검증 |
| 3 | PR-E LEL 제거 (DRF) | 🟢 안전 | enum/fixture/AlarmRecord 9종 일관 |
| 4 | PR-E LEL 잔존 (FastAPI) | 🟠 컨벤션 | 프로토콜 호환성 의도, 동작 무영향 |
| 5 | PR-B `BaseModel.updated_by` 미지정 | 🟡 회귀 가능 | 5곳 — 추적성 손실, 동작 OK |
| 6 | PR-C AlertPolicy + DataRetentionPolicy 시드 | 🟢 안전 | get_or_create idempotent |
| 7 | PR-D Celery 비동기 | 🟢 호출처 / 🟠 운영 가이드 | 호출처 영향 0, 운영 진입 가이드 권장 |
| 8 | PR-G `ThresholdAdmin.list_display` | 🟠 컨벤션 | facility 컬럼 미노출 |

**즉시 깨짐 0건** / **회귀 가능 1건** (PR-B updated_by 5곳) / **컨벤션 4건** / **안전 3건**.

---

## 3. 상세 분석

### 3-1. 🟢 PR-G `evaluate_gas_risk` / `get_threshold` 시그니처 호환성

`get_threshold(group_code, item, facility_id=None)`, `evaluate_gas_risk(gas, value, facility_id=None)`, `invalidate_threshold_cache(group_code, item=None, facility_id=None)` 시그니처에 `facility_id=None` 기본값 추가. 모든 기존 호출자가 호환.

| 호출처 | 코드 | 평가 |
|---|---|---|
| [`apps/monitoring/models/gas_data.py:153`](../../drf-server/apps/monitoring/models/gas_data.py#L153) | `evaluate_gas_risk(gas, value, facility_id=facility_id)` (gas_sensor.facility_id 자동 전달) | ✅ 정상 |
| [`apps/monitoring/views/power_data.py:45`](../../drf-server/apps/monitoring/views/power_data.py#L45) | `get_threshold("power_default", "power_w")` — facility_id 미지정 (의도적) | ✅ 정상 |
| [`apps/alerts/tasks.py:299,355`](../../drf-server/apps/alerts/tasks.py) | `get_threshold("power_default", "power_w")` (×2) | ✅ 정상 |
| [`apps/facilities/services/threshold_service.py:144`](../../drf-server/apps/facilities/services/threshold_service.py) | `evaluate_power_risk(watt)` 내부 `get_threshold("power_default", "power_w")` | ✅ 정상 |

전력은 `power_default` 1개 그룹 (전사) — facility_id 미지정이 정확한 의도. 가스는 `gas_data.recalculate_risks_from_thresholds`가 자동 전달. fastapi-server는 `evaluate_gas_risk` 비사용.

### 3-2. 🟢 PR-G `Threshold.facility` FK + UNIQUE 변경

UNIQUE 제약 `(group, measurement_item)` → `(group, measurement_item, facility)`. 마이그 `0015_threshold_facility_fk.py`로 RemoveConstraint + AddConstraint 단계화. `0016_seed_facility_default_group.py`로 `gas_facility_default` ThresholdGroup 시드 (실제 facility별 row는 운영자 어드민 입력).

`Threshold.objects.create()` 직접 호출처 0건 (마이그/fixture만). 시드 시점에 `facility=None` 전사 row가 기존 9종(가스) + 1종(전력) 유지. 새 환경 `migrate` 검증 완료 (Step 2 fix `0011` 패턴 적용).

### 3-3. 🟢 PR-E LEL 제거 (DRF 측)

| 영역 | 상태 |
|---|---|
| [`apps/core/constants.py:104~`](../../drf-server/apps/core/constants.py) | `GasTypeChoices` 9종 (LEL 제거) ✅ |
| [`apps/reference/migrations/0003_remove_lel.py`](../../drf-server/apps/reference/migrations/0003_remove_lel.py) | CommonCode(group=GAS_TYPE, code='lel') delete ✅ |
| [`apps/alerts/migrations/0010_alter_alarmrecord_gas_type.py`](../../drf-server/apps/alerts/migrations/0010_alter_alarmrecord_gas_type.py) | AlarmRecord.gas_type choices 9종 ✅ |
| [`apps/monitoring/models/gas_data.py`](../../drf-server/apps/monitoring/models/gas_data.py) | 9종 컬럼만 (lel 컬럼 부재) ✅ |
| [`apps/alerts/serializers/alarm_record.py:45`](../../drf-server/apps/alerts/serializers/alarm_record.py) | `if obj.gas_type and obj.measured_value is not None:` — gas_type 9종 dict 매칭 ✅ |
| [`apps/alerts/tasks.py:87`](../../drf-server/apps/alerts/tasks.py) | `_GAS_NAME.get(gas_type, gas_type.upper())` 9종 dict + fallback ✅ |
| [`apps/reference/tests/test_gas_type_consistency.py`](../../drf-server/apps/reference/tests/test_gas_type_consistency.py) | CI 정합성 자동 통과 (이넘과 DB 동기) ✅ |

historical AlarmRecord row에 `gas_type='lel'` 있어도 dict fallback `.upper()`로 안전 처리. 운영 DB에서는 `0003_remove_lel` 마이그가 LEL CommonCode row 삭제.

### 3-4. 🟠 PR-E LEL 잔존 (FastAPI 측) — 의도적 프로토콜 호환

| 파일 | 위치 | 코드 | 상태 |
|---|---|---|---|
| [`fastapi-server/gas/schemas/gas.py:69,74-76`](../../fastapi-server/gas/schemas/gas.py) | Pydantic 필드 | `lel` 필드 (주석 "임계치 미정의") | 🟠 의도 |
| [`fastapi-server/gas/services/gas_service.py:39`](../../fastapi-server/gas/services/gas_service.py) | raw_payload 보관 | lel 값 그대로 DRF 전달 | 🟠 의도 |
| [`fastapi-server/core/gas_thresholds.py:52-58`](../../fastapi-server/core/gas_thresholds.py) | `calculate_individual_risks` | `if gas != "lel"` 자동 필터 | ✅ 안전 |
| [`fastapi-server/dummies/gas_dummy.py:42,55,68`](../../fastapi-server/dummies/gas_dummy.py) | 더미 페이로드 | lel 값 생성 | 🟠 의도 |
| [`fastapi-server/gas/routers/gas_router.py:42`](../../fastapi-server/gas/routers/gas_router.py) | docstring | "10종" 주석 | 🟠 정정 |
| [`docs/api/openapi-fastapi.json`](../api/openapi-fastapi.json) | OpenAPI | lel 필드 스키마 | 🟠 정정 |

**의도적 잔존**: 펌웨어 페이로드가 lel 값을 보내도 fastapi가 거부하지 않고 raw_payload에 보관. DRF의 `recalculate_risks_from_thresholds`는 9종 컬럼만 처리 (lel 무시). `calculate_individual_risks`도 `if gas != "lel"` 필터 — **서비스 동작 무영향**. 단 docstring/주석 "9종 + LEL" 형식은 정정 권장 (펌웨어 합의 트랙과 묶음).

### 3-5. 🟡 PR-B `BaseModel.updated_by` 미지정 (5곳)

10개 모델이 BaseModel 상속으로 `updated_by` FK 자동 추가. nullable이라 NULL OK이지만 **운영 추적성 손실**:

| 파일 | 라인 | 코드 발췌 | 모델 | 영향 |
|---|---|---|---|---|
| [`apps/alerts/services/event_service.py:78,143`](../../drf-server/apps/alerts/services/event_service.py) | 78,143 | `AlarmRecord.objects.create(...)` (병합/신규 양측) | AlarmRecord | 알람 발생자 추적 불가 |
| [`apps/alerts/services/event_service.py:127`](../../drf-server/apps/alerts/services/event_service.py) | 127 | `Event.objects.create(...)` | Event | 이벤트 생성자 추적 불가 |
| [`apps/notifications/services/notification_service.py:63`](../../drf-server/apps/notifications/services/notification_service.py) | 51-63 | `Notification.objects.bulk_create(...)` | Notification | bulk_create는 auto_now 미발동 — `updated_at`도 NULL 가능 |
| [`apps/monitoring/serializers/power_data.py:52`](../../drf-server/apps/monitoring/serializers/power_data.py) | 52 | `PowerEvent.objects.create(...)` | PowerEvent | 측정 소스 불명확 |
| [`apps/safety/services/check_service.py:48`](../../drf-server/apps/safety/services/check_service.py) | 48 | `SafetyStatus.objects.get_or_create(defaults={...})` | SafetyStatus | 체크 작업자 → worker_id로 분리 추적 가능하나 컨벤션 불일치 |
| [`apps/positioning/services/position_service.py:168`](../../drf-server/apps/positioning/services/position_service.py) | 168 | `WorkerPosition.objects.create(...)` | WorkerPosition | 위치 데이터 출처 불명확 (FastAPI/외부 GPS) |

**Notification.bulk_create의 추가 영향**: Django는 `bulk_create`에서 `auto_now` / `auto_now_add` 트리거 안 함. `created_at`은 `auto_now_add` default라 ORM 측에서 NULL이지만 DB default로 채워질 가능성 있음 (DB 의존). `updated_at`은 명시 안 하면 NULL.

**권장 fix 패턴**:
```python
# 시스템 작업자 정의 (CustomUser 모델에 is_system 필드 추가 후)
from django.contrib.auth import get_user_model
User = get_user_model()
system_user = User.objects.filter(is_system=True).first()

AlarmRecord.objects.create(..., updated_by=system_user)
```

→ **후속 트랙**: `system_user(is_system=True)` 도입 정책 결정 후 5곳 일괄 처리. 단순 시스템 사용자 1명으로 마킹할지, 도메인별로 분리할지 운영 정책 결정 필요.

### 3-6. 🟢 PR-C AlertPolicy + DataRetentionPolicy 시드

| 시드 | 패턴 | 검증 |
|---|---|---|
| `0009_seed_alert_policy_default.py` | `get_or_create(event_type, target_facility=None, name, defaults={...})` | ✅ idempotent |
| `0003_seed_data_retention_default.py` | `get_or_create(device_type, data_category, defaults={...})` | ✅ idempotent |

외부 호출자 `.create()` 직접 호출 grep 결과:
- AlertPolicy: 어드민 form / view에서 직접 호출 0건 (Phase 4 PR2 정책 매칭 흐름은 service 레이어 `save_policy()` 사용 권장 — phase_4_pr2_report §6-3)
- DataRetentionPolicy: 마이그 외 호출 0건

기존 단위 테스트 2건 (`test_data_retention.py`, `test_policy_matcher.py`)은 PR-C에서 setUp에 `objects.all().delete()` 추가로 충돌 회피 처리 완료.

**권장 후속**: `AlertPolicy`에 명시적 `UniqueConstraint(event_type, target_facility, name)` 추가 검토 (운영자 어드민 입력 시 중복 회피). 운영 진입 후 정책 결정.

### 3-7. 🟢/🟠 PR-D Celery 비동기

| 항목 | 상태 |
|---|---|
| 호출처 영향 | 🟢 0건 — DBLogHandler.emit + alerts/tasks._push_to_ws 외 직접 INSERT 0 |
| 재귀 가드 | 🟢 thread-local `_guard` 정상 (sync/async 모두) |
| broker fallback | 🟡 `except Exception` 광범위 — kombu/Redis 특정 예외 미분류 |
| Worker 가동 가이드 | 🟠 README/.env.example에 부재 — K8s 배포 시 worker pod 분리 필수 |
| IntegrationLog 손실 감지 | 🟠 fastapi/drf 양측 silent fail — 모니터링 정책 부재 |

**권장 후속 (K8s 배포 시점)**:
1. `db_handler.py`의 except를 `(ImportError, TypeError, kombu.exceptions.OperationalError)`로 범위 축소
2. README에 worker pod 가동 가이드 추가:
   ```bash
   celery -A config worker -l info --concurrency=4
   celery -A config beat -l info  # data_retention_daily 스케줄
   ```
3. 운영 모니터링: Redis 메모리 + 큐 길이 + IntegrationLog 일일 생성율
4. `.env.example`에 `APPLOG_FORCE_SYNC=False` (운영) / `True` (테스트) 명시

### 3-8. 🟠 PR-G `ThresholdAdmin.list_display` facility 컬럼

[`apps/facilities/admin.py`](../../drf-server/apps/facilities/admin.py) `ThresholdAdmin.list_display`에 `facility` 컬럼 미노출. PR-G에서 facility FK 추가됐지만 admin UI에서 facility specific row 식별이 어려움. 어드민 화면 구현 트랙(A 트랙)과 함께 보강 권장.

---

## 4. 결론

### 4-1. 즉시 깨짐 0건 — 운영 진입 단계 OK

본 브랜치 `feature/0508_refactory` 19 commits + overview 1건 (`f6bec42`) 총 20 commits는 **main 머지 가능 상태**. 발견된 모든 권장 사항은 silent 추적성 손실 또는 운영 진입 가이드 부재 — 동작 무영향.

### 4-2. 후속 트랙 분리 권장 (사용자 결정)

| 항목 | 진행 시점 | 분류 |
|---|---|---|
| **`updated_by` 5곳 fix** | `system_user(is_system=True)` 도입 정책 결정 후 | 별도 PR |
| **fastapi LEL 주석 정정** (gas_router.py / openapi-fastapi.json / dummies 주석) | 펌웨어 합의 트랙 (B-11과 묶음) | 외부 합의 후 |
| **Celery 운영 가이드** (worker pod / .env / 모니터링) | K8s 배포 시점 | 인프라 결정 후 |
| **`ThresholdAdmin.list_display` facility 컬럼** | 어드민 화면 구현 트랙 (A) | 명세 도착 후 |
| **`AlertPolicy` UNIQUE 명시** | 운영자 어드민 입력 정책 결정 후 | 운영 진입 후 |

본 분석은 read-only — 코드 변경 없음. 후속 트랙은 외부 의존(인프라/명세/합의)으로 본 세션 외 진행.

---

## 5. 참조 문서

### 5-1. 본 분석 대상 보고서 (10개)
- [post_phase4_step2_report.md](post_phase4_step2_report.md) — POWER_THRESHOLDS DB 일원화
- [post_phase4_b_track_pr_a~h_report.md](post_phase4_b_track_pr_a_report.md) — PR-A~H 8건

### 5-2. 회귀 점검 선행 (3개)
- [post_phase4_step1_report.md](post_phase4_step1_report.md) — Phase 1~4 정적 영향 분석
- [post_phase4_step3_report.md](post_phase4_step3_report.md) — 5종 회귀 테스트
- [post_phase4_b_track_overview.md](post_phase4_b_track_overview.md) — 19 commits 종합 reference

### 5-3. 메모리 (의사결정 근거)
- `sensor_spec_truth_source.md` — 센서 정의서 9종, LEL 미포함 결정 근거 (PR-E)

---

## 6. 분석 방식 메모

본 분석은 **3 Explore 에이전트 parallel** + grep 기반 정적 분석:

1. Agent 1: PR-G facility 시그니처 + PR-E LEL 영향 (가스 도메인)
2. Agent 2: PR-B updated_by 누락 + PR-C 시드 영향 (모델/시드)
3. Agent 3: PR-D Celery 비동기 + 운영 가이드 (운영 인프라)

각 에이전트가 독립 grep + 호출처 매핑 → 본 보고서에서 종합. 회귀 점검 Step 1 동일 패턴 (Phase 1~4 영향 분석)을 PR-A~H에 적용.

다음 분석 시점: 후속 트랙(B-11 / 화면 / 펌웨어 합의) 진입 후 동일 형식 추가 권장.
