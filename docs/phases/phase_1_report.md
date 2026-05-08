# Phase 1 — 기반 통합 PR 보고서

> 작업일: 2026-05-08
> 브랜치: `feature/0508_refactory`
> 부모 plan: [.claude/plans/swirling-mixing-torvalds.md](../../.claude/plans/swirling-mixing-torvalds.md)
> 구현 plan: [.claude/plans/verdant-cascading-nebula.md](../../.claude/plans/verdant-cascading-nebula.md)

---

## 1. 작업 목적

ISH/CJY/imsi 3개 분석 plan + 정휘훈 4차 결정 분석을 통합 적용하기 위한 **기반 통합 PR**.

각 plan을 독립적으로 진행하면 같은 파일·이넘·모델을 동시에 수정해 마이그레이션 충돌·재작업이 발생하므로, 충돌 가능 지점을 1개 PR로 모아 일괄 해소하고 후속 Phase 2~4 PR이 의존할 수 있는 기반을 만든다.

본 PR은 **모델·이넘·앱 신설 위주**이며 도메인별 화면/서비스 변경은 Phase 2 이후로 분리.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `python manage.py check` | ✅ 통과 (0 issues) |
| 마이그레이션 일관성 | `python manage.py makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그레이션 적용 | `python manage.py migrate` | ✅ 모든 마이그레이션 적용 + RiskLevelStandard 3 row + GAS_TYPE 11 row 시드 |
| 단위 테스트 | `python manage.py test apps.reference.tests.test_gas_type_consistency apps.core.tests.test_risk_level_standard_consistency` | ✅ 3 tests OK |
| ruff lint | `pre-commit run --files <변경파일>` | ✅ Passed |
| ruff-format | 동일 | ✅ Passed (15개 파일 자동 포맷팅 1회 후 재실행 통과) |

### 시드 데이터 확인

```bash
python manage.py shell -c "
from apps.core.models import RiskLevelStandard
from apps.reference.models import CommonCode
print(list(RiskLevelStandard.objects.values_list('code', 'name', 'display_color', 'event_priority')))
print(list(CommonCode.objects.filter(group__code='GAS_TYPE').values_list('code', flat=True)))
"
# 출력:
# [('normal','정상','green',1), ('warning','주의','orange',2), ('danger','위험','red',3)]
# ['co','h2s','co2','o2','no2','so2','o3','nh3','voc','lel']
```

### CI 정합성 테스트 통과

- `test_gas_type_enum_matches_common_code` — `GasTypeChoices` ↔ `CommonCode(GAS_TYPE)` 키 목록 일치
- `test_enum_matches_db` — `RiskLevel` ↔ `RiskLevelStandard.code` 일치
- `test_priority_unique` — `RiskLevelStandard.event_priority` 중복 없음

---

## 3. 변경 파일 — 신규 (역할별)

### 3-1. 신규 앱 디렉토리 (2개)

| 경로 | 역할 |
|---|---|
| [drf-server/apps/operations/](../../drf-server/apps/operations/) | 운영 중 쌓이는 로그·정책 (AppLog/IntegrationLog는 Phase 2 예정, DataRetentionPolicy 신설) |
| [drf-server/apps/reference/](../../drf-server/apps/reference/) | 운영자가 어드민에서 편집하는 공통 코드 마스터 (CodeGroup, CommonCode) |

각 앱 디렉토리에 보일러플레이트 6종(`__init__.py`, `apps.py`, `admin.py`, `models/__init__.py`, `migrations/__init__.py`, `tests/__init__.py`).

### 3-2. 신규 모델 파일

| 파일 | 모델 | 역할 |
|---|---|---|
| [drf-server/apps/core/models/risk_level_standard.py](../../drf-server/apps/core/models/risk_level_standard.py) | `RiskLevelStandard` | 위험 단계 메타데이터 (code/name/display_color/alert_intensity/event_priority). RiskLevel 이넘과 1:1 강제 매핑 |
| [drf-server/apps/reference/models/code_group.py](../../drf-server/apps/reference/models/code_group.py) | `CodeGroup` | 공통 코드 그룹 마스터 (GAS_TYPE/DEVICE_TYPE 등) |
| [drf-server/apps/reference/models/common_code.py](../../drf-server/apps/reference/models/common_code.py) | `CommonCode` | CodeGroup 내 개별 코드값. UNIQUE(group, code) |
| [drf-server/apps/accounts/models/role_profile.py](../../drf-server/apps/accounts/models/role_profile.py) | `RoleProfile` | UserType 4종 외 사용자 정의 역할. Phase 2-c Menu/RoleMenuVisibility에서 활용 |
| [drf-server/apps/operations/models/data_retention_policy.py](../../drf-server/apps/operations/models/data_retention_policy.py) | `DataRetentionPolicy` | 데이터 보관 정책 (gas/power/position 횡단). Phase 4-g Celery 태스크가 본 모델 순회 |

### 3-3. fixture (2개)

| 파일 | 시드 내용 |
|---|---|
| [drf-server/apps/core/fixtures/risk_level_standard.json](../../drf-server/apps/core/fixtures/risk_level_standard.json) | RiskLevelStandard 3 row (`normal`/`warning`/`danger`) — RiskLevel 이넘과 1:1 |
| [drf-server/apps/reference/fixtures/gas_type.json](../../drf-server/apps/reference/fixtures/gas_type.json) | CodeGroup 1 (`GAS_TYPE`) + CommonCode 10 (CO/H2S/CO2/O2/NO2/SO2/O3/NH3/VOC/LEL) |

### 3-4. 마이그레이션 (8개)

| 파일 | 역할 |
|---|---|
| accounts/0009_roleprofile.py | RoleProfile 모델 생성 |
| alerts/0003_alter_alarmrecord_alarm_type_alter_event_event_type.py | AlarmRecord/Event의 alarm_type/event_type choices 갱신 (10종) |
| core/0003_systemlog_result_systemlog_target_menu_and_more.py | SystemLog 필드 3개 추가 + ActionType choices 갱신 + RiskLevelStandard 모델 |
| core/0004_seed_risk_level_standard.py | RunPython으로 fixture 자동 로드 (마이그레이션 시점 시드) |
| facilities/0009_equipment_updated_by_alter_equipment_created_at_and_more.py | Equipment의 BaseModel 상속 변경 (updated_by FK 추가, verbose_name 정합) |
| operations/0001_initial.py | DataRetentionPolicy 모델 생성 |
| reference/0001_initial.py | CodeGroup, CommonCode 모델 생성 |
| reference/0002_seed_gas_type.py | RunPython으로 GAS_TYPE 그룹 + 10개 코드 시드 |
| safety/0002_safetycheckitem_updated_by_and_more.py | SafetyCheckItem의 BaseModel 상속 변경 (updated_by FK 추가) |

### 3-5. CI 정합성 테스트 (2개)

| 파일 | 검증 |
|---|---|
| [drf-server/apps/reference/tests/test_gas_type_consistency.py](../../drf-server/apps/reference/tests/test_gas_type_consistency.py) | `GasTypeChoices` 이넘 ↔ `CommonCode(GAS_TYPE)` 키 목록 일치 |
| [drf-server/apps/core/tests/test_risk_level_standard_consistency.py](../../drf-server/apps/core/tests/test_risk_level_standard_consistency.py) | `RiskLevel` 이넘 ↔ `RiskLevelStandard.code` 일치 + event_priority 중복 검증 |

---

## 4. 변경 파일 — 기존 수정

### 4-1. 설정 / 이넘 / 상수

| 파일 | 변경 내용 |
|---|---|
| [drf-server/config/settings.py](../../drf-server/config/settings.py) | `INSTALLED_APPS`에 `apps.operations`, `apps.reference` 2줄 추가 |
| [drf-server/apps/core/constants.py](../../drf-server/apps/core/constants.py) | `AlarmType` 4종 → 10종 (PPE_VIOLATION/VR_TRAINING_NOT_DONE/SAFETY_CHECK_PENDING/INSPECTION_SCHEDULED/BATCH_FAILED/STORAGE_OVERDUE 추가, 기존 4종 라벨만 통일). `USER_FACING_ALARM_TYPES` 9종 추가 (SENSOR_FAULT 제외) |

### 4-2. SystemLog 확장

| 파일 | 변경 내용 |
|---|---|
| [drf-server/apps/core/models/system_log.py](../../drf-server/apps/core/models/system_log.py) | 필드 3개 추가 (`target_menu` Menu.code 문자열 참조, `target_name` 삭제 객체 이름 스냅샷, `result` success/failure choices) + ActionType 17종 추가 (MAP_* 5 + POLICY_* 3 + NOTICE_* 3 + VR_* 3 + CHECKLIST_* 3) + `Result` 내부 TextChoices 클래스 + action_type max_length 30 → 40 |
| [drf-server/apps/core/admin.py](../../drf-server/apps/core/admin.py) | SystemLog 어드민에 신규 필드 표시 (target_menu/result), search_fields 확장. RiskLevelStandard 어드민 신규 등록 (`readonly_fields = ['code', ...]` — 운영자 임의 변경 차단) |

### 4-3. accounts

| 파일 | 변경 내용 |
|---|---|
| [drf-server/apps/accounts/models/__init__.py](../../drf-server/apps/accounts/models/__init__.py) | `RoleProfile` re-export 추가 |
| [drf-server/apps/accounts/admin.py](../../drf-server/apps/accounts/admin.py) | `RoleProfileAdmin` 등록 |
| [drf-server/apps/accounts/migrations/0003_loginlog.py](../../drf-server/apps/accounts/migrations/0003_loginlog.py) | **noop fix** — 0001_initial이 partial LoginLog 생성, 0002_initial이 user FK + indexes 추가로 완전체화. 0003의 CreateModel은 잘못 생성된 중복이라 새 환경에서 `table already exists` 충돌 → `operations = []` 빈 리스트로 변경. 운영 DB는 이미 적용 처리되어 영향 없음 |

### 4-4. core

| 파일 | 변경 내용 |
|---|---|
| [drf-server/apps/core/models/__init__.py](../../drf-server/apps/core/models/__init__.py) | `RiskLevelStandard` re-export 추가 |

### 4-5. facilities — Equipment

| 파일 | 변경 내용 |
|---|---|
| [drf-server/apps/facilities/models/equipment.py](../../drf-server/apps/facilities/models/equipment.py) | `models.Model` → `BaseModel` 상속 (updated_by FK 자동 추가). `equipment_code` property `EQP-{id:03d}` → `FAC-{id:03d}`. `deactivate(updated_by=None)` 시그니처 변경 |
| [drf-server/apps/facilities/serializers/facility_admin.py](../../drf-server/apps/facilities/serializers/facility_admin.py) | `get_equipment_code`의 prefix `EQP-` → `FAC-` |
| [drf-server/apps/facilities/views/facility_admin.py](../../drf-server/apps/facilities/views/facility_admin.py) | 검색 prefix `EQP-` → `FAC-`. POST/PUT의 `serializer.save()` → `serializer.save(updated_by=request.user)`. DELETE 단건 + bulk delete의 `equipment.deactivate()` → `equipment.deactivate(updated_by=request.user)` |

### 4-6. safety — SafetyCheckItem

| 파일 | 변경 내용 |
|---|---|
| [drf-server/apps/safety/models/safety.py](../../drf-server/apps/safety/models/safety.py) | `SafetyCheckItem`: `models.Model` → `BaseModel` 상속. `deactivate(updated_by=None)` 시그니처 변경. SafetyStatus는 변경 없음 (UNIQUE 변경은 Phase 3-c) |

---

## 5. 사용자 결정 사항 (Phase 1 진입 전 확정)

부모 plan §0의 사전 결정 3건이 본 PR에 반영됨.

### 5-1. AlarmType 10종

```python
# 기존 4종 (키/값 변경 없음, 라벨만 통일)
GAS_THRESHOLD, POWER_OVERLOAD, GEOFENCE_INTRUSION, SENSOR_FAULT
# 신규 6종
PPE_VIOLATION, VR_TRAINING_NOT_DONE, SAFETY_CHECK_PENDING,
INSPECTION_SCHEDULED, BATCH_FAILED, STORAGE_OVERDUE
# 정책 화면 노출 9종 (SENSOR_FAULT 제외)
USER_FACING_ALARM_TYPES = [...]
```

### 5-2. SystemLog ActionType 17종 추가

MAP_* 5 + POLICY_* 3 (DEACTIVATED) + NOTICE_* 3 + VR_CONTENT_* 3 + CHECKLIST_* 3.

CHECKLIST_REVISION_PUBLISHED / CHECKLIST_SECTION_CREATED / CHECKLIST_ITEM_DEACTIVATED — 일관성을 위해 모두 `CHECKLIST_` prefix 통일.

### 5-3. RiskLevelStandard 토큰 진입

`display_color`는 토큰명(`green`/`orange`/`red`)으로 시작 — 디자이너 hex 회신 시 데이터 마이그레이션 1회로 갱신 가능. `event_priority`/`alert_intensity`는 백엔드 운영 정책 확정값.

---

## 6. 발견 사항 / 부수 작업

### 6-1. 기존 결함 fix — `accounts/0003_loginlog.py`

**증상:** 새 테스트 DB 생성 시 `table "login_log" already exists` 충돌로 모든 테스트 차단.

**원인:** 마이그레이션 history가 `0001_initial` (partial LoginLog) → `0002_initial` (user FK + 4 indexes 추가) → `0003_loginlog` (전체 CreateModel **다시**)로 구성되어 있음. 0003가 잘못 자동 생성되어 중복 작업을 시도.

**해결:** 0003_loginlog의 operations를 빈 리스트로 변경 (noop). 운영 DB는 이미 0001~0003 모두 "적용됨"으로 표시되어 본 변경 실행 안 됨 → 운영 영향 없음. 새 환경에서는 0001+0002로 LoginLog 완성 → 0003 noop → 충돌 해소.

본 결함은 본 Phase 1 작업 본질과 무관하지만, 테스트 검증 차단으로 인해 함께 수정 (사용자 A안 결정).

### 6-2. AlarmType ↔ HazardType CI 테스트는 Phase 2-a까지 보류

부모 plan §2-2에서 결정된 3개 CI 정합성 테스트 중 AlarmType ↔ HazardType은 HazardType 모델이 Phase 2-a에 신설되므로 본 PR에서는 미작성. Phase 2-a에서 활성화 예정.

### 6-3. 다른 변경하지 않은 항목

부모 plan §1-3에 명시된 미진행 확정 항목들이 본 PR에서도 변경 없음:
- ❌ GasData.ch4 / GasTypeChoices.CH4 (센서 정의서 기준)
- ❌ PowerData.DataType.TEMPERATURE
- ❌ NotificationRecipient/NotificationDeliveryAttempt 분리
- ❌ VRTrainingViewRecord
- ❌ DELAYED 상태 추가

---

## 7. Phase 1 외 / 후속 트랙

본 PR 범위 외 후속 항목 (부모 plan §2-10):
- 피그마 측 CH4/온도 컬럼 제거 협의 (디자인/프론트)
- `GasTypeChoices.LEL` dead code grep + cleanup (별도 PR)
- IntegrationLog `target_system` 식별자 표준화 (Phase 2-e 진입 전)
- BaseModel 컨벤션 일괄 통일 PR (15개+ 직접 정의 모델, 본 PR 외)
- 펌웨어 `node_id` 페이로드 변경 (Phase 3-a 선행조건)
- ACTION_GROUP_MAP 그룹핑 코드 (화면 구현 시점)
- Menu.code 형식 ('SNB-01' vs snake_case) — Phase 2-c에서 결정

---

## 8. 다음 Phase

[verdant-cascading-nebula.md](../../.claude/plans/verdant-cascading-nebula.md) §3 의존 그래프에 따라 **Phase 2 도메인 모델 PR**들이 병렬 가능 상태:

- Phase 2-a: HazardType / HazardTypeGroup (alerts) + seed + AlarmType↔HazardType CI 활성화
- Phase 2-b: Threshold / ThresholdGroup (facilities)
- Phase 2-c: Menu / RoleMenuVisibility (dashboard)
- Phase 2-d: AppLog (operations) + DBLogHandler
- Phase 2-e: IntegrationLog (operations) + DRF internal API
- Phase 2-f: AlertPolicy (alerts) + target_user_types JSON
- Phase 2-g: apps/notices 신설
- Phase 2-h: apps/training 신설
