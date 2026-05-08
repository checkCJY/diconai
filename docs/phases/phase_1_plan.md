# Phase 1 — 기반 통합 PR 구현 plan

## Context

부모 plan [swirling-mixing-torvalds.md](/home/cjy/.claude/plans/swirling-mixing-torvalds.md)의 §3 의존 그래프 [Phase 1] 단계를 단일 PR로 구현하기 위한 구체 작업 plan. ISH/CJY/imsi 3개 분석 plan과 정휘훈 결정 분석을 기반으로 한 통합 결정사항을 1개 PR에 모아 후속 Phase 2~4 PR이 의존할 기반을 만든다.

본 PR은 **모델·이넘·앱 신설 위주**이며 도메인별 화면/서비스 변경은 Phase 2 이후로 미룬다. 변경 영향이 광범위하므로 머지 전 충분한 리뷰가 필요하다.

부모 plan의 사용자 결정사항:
- 신규 앱 2개 동시 신설 (operations + reference)
- Equipment + SafetyCheckItem 둘 다 BaseModel 상속
- CI 정합성 테스트 2종 도입 (AlarmType↔HazardType, GasTypeChoices↔CommonCode)
- RiskLevelStandard.code 데이터 마이그레이션 + UI readonly 병행
- target_user_types JSON 시작 (RoleProfile FK 보류)
- IntegrationLog fire-and-forget 시작

---

## 0. 사전 결정 (확정 ✅)

### 0-1. ✅ AlarmType 10종 확정

기존 4종 키/값 유지(라벨만 통일). 신규 6종 추가. SENSOR_FAULT는 시스템 분류로 남기되 정책 화면에는 비노출(`USER_FACING_ALARM_TYPES`로 분리).

```python
# apps/core/constants.py
class AlarmType(models.TextChoices):
    # 기존 4종 (키/값 변경 없음, 라벨만 통일)
    GAS_THRESHOLD        = "gas_threshold",        "가스 경보"
    POWER_OVERLOAD       = "power_overload",       "전력 이상"
    GEOFENCE_INTRUSION   = "geofence_intrusion",   "위험구역 진입"
    SENSOR_FAULT         = "sensor_fault",         "센서 이상"
    # 신규 6종 (CJY 화면 요구)
    PPE_VIOLATION        = "ppe_violation",        "PPE 미착용"
    VR_TRAINING_NOT_DONE = "vr_training_not_done", "VR 교육 미이수"
    SAFETY_CHECK_PENDING = "safety_check_pending", "작업 안전 체크리스트 미완료"
    INSPECTION_SCHEDULED = "inspection_scheduled", "점검 예정"
    BATCH_FAILED         = "batch_failed",         "배치 실패"
    STORAGE_OVERDUE      = "storage_overdue",      "보관 주기 실패"

USER_FACING_ALARM_TYPES = [
    AlarmType.GAS_THRESHOLD, AlarmType.POWER_OVERLOAD, AlarmType.GEOFENCE_INTRUSION,
    AlarmType.PPE_VIOLATION, AlarmType.VR_TRAINING_NOT_DONE, AlarmType.SAFETY_CHECK_PENDING,
    AlarmType.INSPECTION_SCHEDULED, AlarmType.BATCH_FAILED, AlarmType.STORAGE_OVERDUE,
]
```

데이터 마이그레이션 0회. choices 메타만 갱신.

### 0-2. ✅ SystemLog ActionType 17종 추가

```python
# === MAP_* (5종) ===
MAP_GEOFENCE_CREATE        = "map_geofence_create",        "위험구역 생성 (지도)"
MAP_SENSOR_MOVE            = "map_sensor_move",            "센서 이동"
MAP_FACILITY_UPDATE        = "map_facility_update",        "설비 수정"
MAP_POSITION_NODE_REGISTER = "map_position_node_register", "위치 노드 등록"
MAP_OBJECT_DELETE          = "map_object_delete",          "객체 삭제"

# === POLICY_* (3종, 소프트 삭제이므로 DEACTIVATED) ===
POLICY_CREATED      = "policy_created",      "알림 정책 생성"
POLICY_UPDATED      = "policy_updated",      "알림 정책 수정"
POLICY_DEACTIVATED  = "policy_deactivated",  "알림 정책 비활성화"

# === NOTICE_* (3종) ===
NOTICE_CREATE = "notice_create", "공지 생성"
NOTICE_UPDATE = "notice_update", "공지 수정"
NOTICE_DELETE = "notice_delete", "공지 삭제"

# === VR_* (3종) ===
VR_CONTENT_CREATED  = "vr_content_created",  "VR 콘텐츠 등록"
VR_CONTENT_REPLACED = "vr_content_replaced", "VR 콘텐츠 교체"
VR_CONTENT_TOGGLED  = "vr_content_toggled",  "VR 콘텐츠 활성화 전환"

# === CHECKLIST_* (3종, prefix 통일) ===
CHECKLIST_REVISION_PUBLISHED = "checklist_revision_published", "체크리스트 개정 발행"
CHECKLIST_SECTION_CREATED    = "checklist_section_created",    "체크리스트 섹션 생성"
CHECKLIST_ITEM_DEACTIVATED   = "checklist_item_deactivated",   "체크리스트 항목 비활성화"
```

APPEND-ONLY 모델이라 데이터 변환 불필요.

### 0-3. ✅ RiskLevelStandard fixture 토큰명 진입

`display_color`는 토큰명(green/orange/red) — 디자이너 hex 회신 시 마이그레이션 1회로 갱신. `event_priority`/`alert_intensity`는 백엔드 운영 정책 확정값.

```json
// apps/core/fixtures/risk_level_standard.json
[
  {"model": "core.risklevelstandard", "pk": 1, "fields": {
    "code": "normal",  "name": "정상", "display_color": "green",
    "alert_intensity": "normal",  "event_priority": 1, "is_active": true,
    "description": "정상 운영 상태"}},
  {"model": "core.risklevelstandard", "pk": 2, "fields": {
    "code": "warning", "name": "주의", "display_color": "orange",
    "alert_intensity": "warning", "event_priority": 2, "is_active": true,
    "description": "임계치 근접 — 모니터링 강화 필요"}},
  {"model": "core.risklevelstandard", "pk": 3, "fields": {
    "code": "danger",  "name": "위험", "display_color": "red",
    "alert_intensity": "urgent",  "event_priority": 3, "is_active": true,
    "description": "임계치 초과 — 즉시 조치 필요"}}
]
```

`code`는 lowercase, RiskLevel 이넘과 1:1. 어드민 폼 `readonly_fields = ['code']`로 운영자 임의 변경 차단.

### 0-4. CommonCode 초기 그룹

Phase 1: `GAS_TYPE` 1개 그룹만 시드 (CI 테스트 대상). 그 외 그룹은 Phase 2 이후 도메인 PR에서.

---

## 1. 작업 범위 — Phase 1 PR에 포함되는 항목 (12건)

| # | 작업 | 영향 |
|---|---|---|
| 1 | `apps/operations/` 앱 신설 + INSTALLED_APPS 등록 | settings.py, 신규 디렉토리 |
| 2 | `apps/reference/` 앱 신설 + INSTALLED_APPS 등록 | settings.py, 신규 디렉토리 |
| 3 | `core/constants.py` 확장 (AlarmType + SystemLog ActionType) | core/constants.py |
| 4 | `SystemLog` 필드 3개 추가 (target_menu/result/target_name) + APPEND-ONLY 마이그 호환 | core/models/system_log.py + 마이그레이션 |
| 5 | `reference.CodeGroup` + `reference.CommonCode` 신설 | reference/models/* + 마이그레이션 |
| 6 | `core.RiskLevelStandard` 신설 + RunPython 데이터 마이그레이션(row 3개) + UI readonly 어드민 | core/models/* + 마이그레이션 + admin.py |
| 7 | `accounts.RoleProfile` 신설 | accounts/models/role_profile.py + 마이그레이션 |
| 8 | `operations.DataRetentionPolicy` 신설 (Celery 태스크는 Phase 4-g) | operations/models/* + 마이그레이션 |
| 9 | `Equipment` BaseModel 상속 전환 + `equipment_code` prefix `EQP-`→`FAC-` | facilities/models/equipment.py + facility_admin.py:325 + 마이그레이션 |
| 10 | `SafetyCheckItem` BaseModel 상속 전환 (section FK는 Phase 3-b) | safety/models/safety.py + 마이그레이션 |
| 11 | 어드민 등록 (CodeGroup/CommonCode/RiskLevelStandard/RoleProfile/DataRetentionPolicy) | 각 앱 admin.py |
| 12 | CI 정합성 테스트 골격 (활성화는 Phase 2-a에서 HazardType seed 들어올 때) | apps/{core,reference,alerts}/tests/test_enum_db_consistency.py |

---

## 2. 작업 상세

### 2-1. 신규 앱 2개 신설 (operations, reference)

**기존 패턴 참조:** [drf-server/apps/accounts/apps.py](drf-server/apps/accounts/apps.py), [drf-server/apps/accounts/__init__.py](drf-server/apps/accounts/__init__.py), [drf-server/apps/accounts/models/__init__.py](drf-server/apps/accounts/models/__init__.py).

**신설 파일:**
- `drf-server/apps/operations/__init__.py` (빈 파일)
- `drf-server/apps/operations/apps.py` (`OperationsConfig`, `name="apps.operations"`)
- `drf-server/apps/operations/models/__init__.py` (모델 re-export — Phase 1에서는 `DataRetentionPolicy`만, AppLog/IntegrationLog는 Phase 2에서 추가)
- `drf-server/apps/operations/models/data_retention_policy.py`
- `drf-server/apps/operations/admin.py`
- `drf-server/apps/operations/migrations/__init__.py`
- 동일 구조로 `drf-server/apps/reference/` 신설 (`code_group.py`, `common_code.py`)

**INSTALLED_APPS 등록:** [drf-server/config/settings.py:36-57](drf-server/config/settings.py#L36-L57) `# apps` 섹션에 두 줄 추가:
```python
"apps.operations",
"apps.reference",
```

**검증:** `python manage.py check` → 오류 없이 통과.

---

### 2-2. `core/constants.py` 확장

**대상 파일:** [drf-server/apps/core/constants.py](drf-server/apps/core/constants.py)

**변경:**
- `AlarmType.choices` 확장: 기존 4종 유지 + 0-1에서 확정된 5~6종 추가 (lowercase 값)
- 메뉴 코드 상수 (Menu.code 참조용) — Menu DB는 Phase 2-c에 신설되지만 코드 상수는 Phase 1에서 미리 정의(SystemLog.target_menu에 사용). 형식 결정 필요 (snake_case 또는 'SNB-01' 유지). 부모 plan §2-3 결정 따라 `Menu.code` 문자열 참조이므로 상수만 추가.

**SystemLog ActionType 확장:** [drf-server/apps/core/models/system_log.py](drf-server/apps/core/models/system_log.py)의 `ActionType` 클래스에 추가:
- ISH MAP_*: `MAP_GEOFENCE_CREATE`, `MAP_SENSOR_MOVE`, `MAP_FACILITY_UPDATE`, `MAP_POSITION_NODE_REGISTER`, `MAP_OBJECT_DELETE`
- CJY POLICY_*: `POLICY_CREATE`, `POLICY_UPDATE`, `POLICY_DELETE`
- CJY NOTICE_*: `NOTICE_CREATE`, `NOTICE_UPDATE`, `NOTICE_DELETE`
- CJY VR_*: `VR_CONTENT_REPLACE` (또는 VR_CONTENT_CREATE/UPDATE 분리)
- CJY CHECKLIST_REVISION_*: `CHECKLIST_REVISION_PUBLISH` (필요 시 분리)

값은 모두 lowercase (기존 컨벤션 일치, [system_log.py:18-37](drf-server/apps/core/models/system_log.py#L18-L37) 패턴).

**ACTION_GROUP_MAP** (ISH §8-4): 본 PR에서는 **미포함**. 화면 그룹핑 로직이 들어올 때 별도 PR. 본 PR은 enum 추가만.

---

### 2-3. SystemLog 필드 3개 추가

**대상 파일:** [drf-server/apps/core/models/system_log.py](drf-server/apps/core/models/system_log.py)

**추가 필드:**
```python
target_menu = models.CharField(
    max_length=100, blank=True, default="", verbose_name="대상 메뉴",
    help_text="Menu.code와 일치하는 문자열. FK 아님(이력 보존).",
)
result = models.CharField(
    max_length=10, blank=True, default="success",
    choices=[("success", "성공"), ("failure", "실패")],
    verbose_name="결과",
)
target_name = models.CharField(
    max_length=200, blank=True, default="", verbose_name="대상 이름",
    help_text="삭제된 객체 이름 복원용 스냅샷.",
)
```

**APPEND-ONLY 호환:** 기존 [save() 오버라이드](drf-server/apps/core/models/system_log.py#L96-L102)는 `pk is not None` 조건으로 수정 차단 → 신규 필드 default 값으로 마이그레이션 시 기존 row 자동 채움. 충돌 없음.

**마이그레이션 주의:** 기존 row는 `result="success"`, `target_menu=""`, `target_name=""` default로 채워짐. 화면에서 마이그 시점 이전 row 표시 정책은 Phase 4 화면 구현 시 결정.

---

### 2-4. `reference.CodeGroup` + `reference.CommonCode`

**신설 파일:**
- `drf-server/apps/reference/models/code_group.py`
- `drf-server/apps/reference/models/common_code.py`

**스키마 (imsi plan 기반, 정확한 필드는 [imsi plan 「기준 정보 관리 (공통 코드 관리)」](skill/imsi/) 참조):**
```python
class CodeGroup(BaseModel):
    code = CharField(max_length=50, unique=True, verbose_name="그룹 코드")  # GAS_TYPE 등
    name = CharField(max_length=100, verbose_name="그룹 명")
    description = TextField(blank=True, default="")
    is_active = BooleanField(default=True)
    # BaseModel: created_at, updated_at, updated_by

class CommonCode(BaseModel):
    group = ForeignKey(CodeGroup, on_delete=CASCADE, related_name="codes")
    code = CharField(max_length=50, verbose_name="코드")  # co, h2s 등
    name = CharField(max_length=200, verbose_name="코드 명")
    description = TextField(blank=True, default="")
    sort_order = PositiveIntegerField(default=0)
    is_active = BooleanField(default=True)

    class Meta:
        constraints = [UniqueConstraint(fields=["group", "code"], name="uq_commoncode_group_code")]
        indexes = [Index(fields=["group", "sort_order"])]
```

**Phase 1 seed:** `GAS_TYPE` 그룹 + 9개 코드 (CO/H2S/CO2/O2/NO2/SO2/O3/NH3/VOC). LEL은 dead code 정리 후 결정 (부모 plan §2-10). `RunPython` 데이터 마이그레이션으로 처리.

---

### 2-5. `core.RiskLevelStandard`

**신설 파일:**
- `drf-server/apps/core/models/risk_level_standard.py`
- `drf-server/apps/core/fixtures/risk_level_standard.json` (§0-3 확정 fixture)

**스키마 (확정):**
```python
class RiskLevelStandard(BaseModel):
    class AlertIntensity(TextChoices):
        NORMAL  = "normal",  "정상"
        WARNING = "warning", "주의"
        URGENT  = "urgent",  "긴급"

    code = CharField(max_length=20, unique=True, verbose_name="위험 단계 코드")  # RiskLevel.values와 1:1
    name = CharField(max_length=50, verbose_name="표시 명")
    display_color = CharField(max_length=20, default="green", verbose_name="표시 색상 토큰")
    alert_intensity = CharField(max_length=10, choices=AlertIntensity.choices,
                                default=AlertIntensity.NORMAL, verbose_name="알림 강도")
    event_priority = PositiveSmallIntegerField(default=1, verbose_name="이벤트 우선순위")
    is_active = BooleanField(default=True)
    description = TextField(blank=True, default="")
```

**fixture 적용 방식 (loaddata):** RunPython 마이그레이션에서 `call_command('loaddata', 'risk_level_standard', app_label='core')` 호출 — fixture JSON과 단일 진실 공급원 일치.

```python
# apps/core/migrations/000X_seed_risk_level_standard.py
from django.core.management import call_command
from django.db import migrations

def load_fixture(apps, schema_editor):
    call_command("loaddata", "risk_level_standard", app_label="core")

def revert_fixture(apps, schema_editor):
    apps.get_model("core", "RiskLevelStandard").objects.filter(
        code__in=["normal", "warning", "danger"]
    ).delete()

class Migration(migrations.Migration):
    dependencies = [("core", "000Y_risklevelstandard")]
    operations = [migrations.RunPython(load_fixture, revert_fixture)]
```

**어드민 readonly:** [drf-server/apps/core/admin.py](drf-server/apps/core/admin.py)에 등록:
```python
@admin.register(RiskLevelStandard)
class RiskLevelStandardAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "color", "priority", "map_blink", "updated_at")
    readonly_fields = ("code",)  # 핵심: code는 수정 불가
    fieldsets = (
        (None, {"fields": ("code", "name", "color", "priority", "map_blink", "description")}),
    )
```

`has_add_permission`은 별도 차단하지 않음 (운영자가 추가 row를 만드는 것 자체는 허용 — 다만 code가 RiskLevel과 일치하지 않으면 CI 테스트 fail. 또는 추가도 차단할지는 0-4와 함께 결정).

---

### 2-6. `accounts.RoleProfile`

**신설 파일:** `drf-server/apps/accounts/models/role_profile.py`

**스키마 (imsi 「메뉴관리.md」 기반):**
```python
class RoleProfile(BaseModel):
    code = CharField(max_length=50, unique=True, verbose_name="역할 코드")
    name = CharField(max_length=100, verbose_name="역할 명")
    base_user_type = CharField(
        max_length=20, choices=UserType.choices, verbose_name="기반 사용자 유형",
        help_text="권한 기본값 — 이 RoleProfile을 부여받은 사용자의 user_type 추론용",
    )
    platform_type = CharField(
        max_length=10, default="web",
        choices=[("web", "웹 어드민"), ("app", "모바일 앱")],
    )
    description = TextField(blank=True, default="")
    is_active = BooleanField(default=True)
```

**accounts/models/__init__.py 갱신:** `RoleProfile` re-export 추가.

**CustomUser와의 연결:** Phase 1에서는 **연결 안 함**. 모델만 신설. 사용자 ↔ RoleProfile 매핑은 화면 요구가 들어오는 Phase 2 이후.

---

### 2-7. `operations.DataRetentionPolicy`

**신설 파일:** `drf-server/apps/operations/models/data_retention_policy.py`

**스키마 (ISH §8-7 채택안 그대로, 단 위치만 monitoring → operations):**
```python
class DataRetentionPolicy(BaseModel):
    class DeviceType(TextChoices):
        GAS_SENSOR, POWER, POSITION_NODE
    class DataCategory(TextChoices):
        GAS_RAW, GAS_ANOMALY, POWER_RAW, POWER_AGG, POSITION_HIST
    class DeleteCycle(TextChoices):
        DAILY, MONTHLY_1, MONTHLY_15, MONTHLY_LAST, QUARTERLY

    device_type = CharField(choices=DeviceType.choices, max_length=20)
    data_category = CharField(choices=DataCategory.choices, max_length=20)
    raw_retention_days = PositiveIntegerField(default=30)
    history_retention_days = PositiveIntegerField(default=180)
    delete_cycle = CharField(choices=DeleteCycle.choices, default=DeleteCycle.DAILY, max_length=20)
    is_active = BooleanField(default=True)
    memo = TextField(blank=True, default="")
    manager = ForeignKey(settings.AUTH_USER_MODEL, on_delete=SET_NULL, null=True, blank=True)

    def clean(self):
        if self.history_retention_days < self.raw_retention_days:
            raise ValidationError("이력 보관 기간은 원천 보관 기간 이상이어야 합니다.")

    class Meta:
        constraints = [UniqueConstraint(fields=["device_type", "data_category"],
                                        name="uq_retention_device_category")]
```

**Celery 보관 배치 태스크는 본 PR 미포함** (Phase 4-g).

---

### 2-8. `Equipment` BaseModel 상속 전환 + equipment_code prefix 변경

**대상 파일:** [drf-server/apps/facilities/models/equipment.py](drf-server/apps/facilities/models/equipment.py)

**변경 전 ([현재 코드:14-31](drf-server/apps/facilities/models/equipment.py#L14-L31)):**
```python
class Equipment(models.Model):
    facility = ForeignKey("facilities.Facility", ...)
    power_device = OneToOneField(...)
    name = CharField(...)
    notes = TextField(...)
    is_active = BooleanField(default=True)
    deactivated_at = DateTimeField(null=True, blank=True)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    @property
    def equipment_code(self):
        return f"EQP-{self.id:03d}"

    def deactivate(self):
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.save(update_fields=["is_active", "deactivated_at", "updated_at"])
        if self.power_device_id:
            self.power_device.deactivate()
```

**변경 후:**
```python
from apps.core.models.base import BaseModel

class Equipment(BaseModel):  # ← 변경
    facility = ForeignKey("facilities.Facility", ...)
    power_device = OneToOneField(...)
    name = CharField(...)
    notes = TextField(...)
    is_active = BooleanField(default=True)
    deactivated_at = DateTimeField(null=True, blank=True)
    # created_at / updated_at / updated_by 는 BaseModel에서 상속

    @property
    def equipment_code(self):
        return f"FAC-{self.id:03d}"  # ← prefix 변경

    def deactivate(self, updated_by=None):  # ← 시그니처 변경
        self.is_active = False
        self.deactivated_at = timezone.now()
        if updated_by is not None:
            self.updated_by = updated_by
        self.save(update_fields=[
            "is_active", "deactivated_at", "updated_at", "updated_by",
        ])
        if self.power_device_id:
            self.power_device.deactivate()
```

**주의 — Meta 명시 상속:** [BaseModel.Meta abstract=True](drf-server/apps/core/models/base.py#L17-L19)이라 Equipment에 기존 Meta가 없으면 그대로 상속. 단, 기존 db_table/indexes/ordering이 정의되어 있다면 Meta(BaseModel.Meta) 명시 상속 필요. 본 모델은 Meta 정의가 없어 영향 없음.

**호출자 갱신:**
- [drf-server/apps/facilities/views/facility_admin.py:325](drf-server/apps/facilities/views/facility_admin.py#L325) `startswith("EQP-")` → `startswith("FAC-")`
- `Equipment.deactivate()` 호출자(DELETE 단건/bulk delete): `serializer.save(updated_by=request.user)` 또는 `instance.deactivate(updated_by=request.user)` 패턴으로 갱신
- View의 POST/PUT: `serializer.save(updated_by=request.user)` 추가

**마이그레이션:**
1. `updated_by` 컬럼 추가 (nullable)
2. 기존 row의 `updated_by`는 NULL 유지 (백필 안 함)
3. `created_at`/`updated_at` 정의 충돌 없음 — BaseModel 정의가 그대로 적용 (필드명·옵션 동일)

---

### 2-9. `SafetyCheckItem` BaseModel 상속 전환

**대상 파일:** [drf-server/apps/safety/models/safety.py:7-44](drf-server/apps/safety/models/safety.py#L7-L44)

**변경:** Equipment와 동일 패턴.
```python
class SafetyCheckItem(BaseModel):  # ← 변경
    facility = ForeignKey("facilities.Facility", on_delete=CASCADE, related_name="safety_check_items")
    title = CharField(max_length=200)
    description = TextField(blank=True, default="")
    order = PositiveSmallIntegerField(default=0)
    is_required = BooleanField(default=True)
    is_active = BooleanField(default=True)
    deactivated_at = DateTimeField(null=True, blank=True)

    def deactivate(self, updated_by=None):
        ...
```

**section FK 추가는 Phase 3-b.** 본 PR은 BaseModel 전환만.

**SafetyStatus는 변경 없음** (UNIQUE 변경은 Phase 3-c).

---

### 2-10. 어드민 등록

각 신규 모델에 대해 [drf-server/apps/accounts/admin.py 패턴](drf-server/apps/accounts/admin.py) 참조해 등록:
- `reference/admin.py`: CodeGroup, CommonCode (list_display = code, name, is_active 등; CodeGroup는 inline으로 CommonCode 표시 검토)
- `core/admin.py`: RiskLevelStandard (§2-5에 readonly 명시)
- `accounts/admin.py`: RoleProfile (기존 admin.py에 register 추가)
- `operations/admin.py`: DataRetentionPolicy (manager FK는 raw_id 또는 dropdown)

---

### 2-11. CI 정합성 테스트 골격

**파일 신설:**
- `drf-server/apps/alerts/tests/test_alarm_type_consistency.py` (Phase 2-a 활성화 — HazardType seed 진입 시점)
- `drf-server/apps/reference/tests/test_gas_type_consistency.py` (CommonCode GAS_TYPE seed가 Phase 1 §2-4에 들어가므로 Phase 1에서 활성화 가능)

**예시 골격 (`reference` 측):**
```python
# apps/reference/tests/test_gas_type_consistency.py
from django.test import TestCase
from apps.core.constants import GasTypeChoices
from apps.reference.models import CodeGroup, CommonCode

class GasTypeConsistencyTest(TestCase):
    def test_gas_type_enum_matches_common_code(self):
        try:
            group = CodeGroup.objects.get(code="GAS_TYPE")
        except CodeGroup.DoesNotExist:
            self.fail("CodeGroup(GAS_TYPE)이 마이그레이션 시드에 없습니다.")
        db_codes = set(group.codes.filter(is_active=True).values_list("code", flat=True))
        enum_codes = set(GasTypeChoices.values)
        # LEL은 dead code 정리 전까지 enum에만 존재 — 별도 결정 후 처리
        self.assertEqual(
            db_codes - {"lel"}, enum_codes - {"lel"},
            f"불일치: enum-only={enum_codes - db_codes}, db-only={db_codes - enum_codes}",
        )
```

**HazardType 측 골격은 Phase 2-a까지 placeholder (skip 또는 미커밋).**

**테스트 실행:** `python manage.py test apps.reference.tests` (pytest 없음).

---

## 3. 마이그레이션 순서 (단일 PR 내)

1. `apps.operations` 초기 마이그레이션 (DataRetentionPolicy)
2. `apps.reference` 초기 마이그레이션 (CodeGroup, CommonCode) + `RunPython` GAS_TYPE 시드
3. `apps.core` 마이그레이션:
   - SystemLog 필드 3개 추가 (default 값 자동 채움)
   - RiskLevelStandard 신설 + `RunPython` 3 row 시드
4. `apps.accounts` 마이그레이션 (RoleProfile)
5. `apps.facilities` 마이그레이션 (Equipment.updated_by FK 추가)
6. `apps.safety` 마이그레이션 (SafetyCheckItem.updated_by FK 추가)

각 단계 사이 의존성 없음 (Equipment/SafetyCheckItem의 BaseModel 상속은 core가 이미 존재하므로 순서 무관). Django는 자동으로 의존성 정렬.

**검증:** `python manage.py makemigrations --dry-run --check` → 변경 없이 통과 (모든 변경이 마이그레이션에 반영됨).

---

## 4. 검증 방법

### 4-1. 빌드 검증
```bash
cd drf-server
python manage.py check                       # Django 시스템 검사
python manage.py makemigrations --dry-run    # 마이그레이션 누락 검증
python manage.py migrate                     # 실제 적용
```

### 4-2. 시드 데이터 확인
```bash
python manage.py shell -c "
from apps.core.models import RiskLevelStandard
from apps.reference.models import CodeGroup, CommonCode
print('RiskLevelStandard:', list(RiskLevelStandard.objects.values_list('code', flat=True)))
print('GAS_TYPE codes:', list(CommonCode.objects.filter(group__code='GAS_TYPE').values_list('code', flat=True)))
"
```
기대: `['normal', 'warning', 'danger']`, 9개 가스 코드.

### 4-3. CI 정합성 테스트
```bash
python manage.py test apps.reference.tests.test_gas_type_consistency
```
기대: 통과 (LEL 예외 처리 후).

### 4-4. 어드민 동작
- 어드민 로그인 후 `/admin/core/risklevelstandard/<id>/change/` 진입 → `code` 필드 readonly 표시 확인
- `/admin/reference/codegroup/` → GAS_TYPE 그룹 표시 확인
- `/admin/operations/dataretentionpolicy/add/` → `clean()` 검증 동작 (history < raw 입력 시 ValidationError)

### 4-5. Equipment 마이그레이션 회귀
```bash
python manage.py shell -c "
from apps.facilities.models import Equipment
e = Equipment.objects.first()
if e:
    print('equipment_code:', e.equipment_code)  # 'FAC-001' 확인
    print('updated_by:', e.updated_by)          # None
"
```

### 4-6. APPEND-ONLY 회귀
SystemLog 기존 row가 새 필드 default로 채워졌는지 확인 + APPEND-ONLY 정책(save/delete 차단) 그대로 동작.

### 4-7. ruff/pre-commit
```bash
pre-commit run --all-files
```
기대: 신규 파일 모두 ruff-format 통과 (88자 제한, [pre-commit-config.yaml](.pre-commit-config.yaml)).

---

## 5. Critical Files (PR 변경 대상)

**신규 디렉토리:**
- [drf-server/apps/operations/](drf-server/apps/operations/)
- [drf-server/apps/reference/](drf-server/apps/reference/)

**신규 파일:**
- `drf-server/apps/operations/{__init__,apps,admin}.py` + `models/{__init__,data_retention_policy}.py` + `migrations/__init__.py`
- `drf-server/apps/reference/{__init__,apps,admin}.py` + `models/{__init__,code_group,common_code}.py` + `migrations/__init__.py`
- `drf-server/apps/core/models/risk_level_standard.py`
- `drf-server/apps/accounts/models/role_profile.py`
- `drf-server/apps/{reference,alerts}/tests/test_*_consistency.py`

**수정 파일:**
- [drf-server/config/settings.py](drf-server/config/settings.py) (INSTALLED_APPS 2줄 추가)
- [drf-server/apps/core/constants.py](drf-server/apps/core/constants.py) (AlarmType 확장 + 메뉴 코드 상수)
- [drf-server/apps/core/models/system_log.py](drf-server/apps/core/models/system_log.py) (필드 3개 + ActionType 다수 추가)
- [drf-server/apps/core/models/__init__.py](drf-server/apps/core/models/__init__.py) (RiskLevelStandard re-export)
- [drf-server/apps/core/admin.py](drf-server/apps/core/admin.py) (RiskLevelStandard readonly 등록)
- [drf-server/apps/accounts/models/__init__.py](drf-server/apps/accounts/models/__init__.py) (RoleProfile re-export)
- [drf-server/apps/accounts/admin.py](drf-server/apps/accounts/admin.py) (RoleProfile 등록)
- [drf-server/apps/facilities/models/equipment.py](drf-server/apps/facilities/models/equipment.py) (BaseModel 상속 + prefix)
- [drf-server/apps/facilities/views/facility_admin.py](drf-server/apps/facilities/views/facility_admin.py) (line 325 + write view에 updated_by 전달)
- [drf-server/apps/safety/models/safety.py](drf-server/apps/safety/models/safety.py) (SafetyCheckItem BaseModel 상속)
- [drf-server/apps/safety/views/...](drf-server/apps/safety/) (SafetyCheckItem write view에 updated_by 전달)

**참조 (변경 없음):**
- [drf-server/apps/core/models/base.py](drf-server/apps/core/models/base.py) (BaseModel 그대로 사용)
- [drf-server/apps/monitoring/migrations/0004_backfill_powerdata_comm_failure.py](drf-server/apps/monitoring/migrations/0004_backfill_powerdata_comm_failure.py) (RunPython 패턴 참조)

---

## 6. 실행 체크리스트

PR 진입 전 확정 (§0):
- [ ] AlarmType 9~10종 키 목록 확정 → core/constants.py 적용
- [ ] SystemLog ActionType 추가 키 목록 확정 → 1차 초안 review
- [ ] CommonCode 초기 그룹 (GAS_TYPE 외 추가 여부) 결정
- [ ] RiskLevelStandard 메타값 (특히 색상) 디자인 협의

구현 순서:
- [ ] `apps/operations/` + `apps/reference/` 보일러플레이트 (apps.py, __init__.py)
- [ ] settings.py INSTALLED_APPS 등록 + `manage.py check` 통과
- [ ] core/constants.py 확장 (AlarmType + 메뉴 코드 상수)
- [ ] SystemLog 필드 3개 + ActionType 추가 + 마이그레이션
- [ ] RiskLevelStandard 모델 + RunPython 시드 마이그레이션
- [ ] CodeGroup + CommonCode 모델 + RunPython GAS_TYPE 시드 마이그레이션
- [ ] RoleProfile 모델 + 마이그레이션
- [ ] DataRetentionPolicy 모델 + 마이그레이션
- [ ] Equipment BaseModel 상속 전환 + equipment_code prefix + 호출자 갱신
- [ ] SafetyCheckItem BaseModel 상속 전환 + 호출자 갱신
- [ ] 어드민 등록 (5개 모델)
- [ ] CI 정합성 테스트 골격 작성 (GAS_TYPE 활성, HazardType placeholder)
- [ ] `manage.py migrate` 클린 환경에서 통과
- [ ] `manage.py test` 통과
- [ ] `pre-commit run --all-files` 통과

머지 후:
- [ ] Phase 2-a (HazardType 신설) 시작 가능 안내

---

## 7. 미해결 / Phase 1 외 항목

본 plan 범위 외 (부모 plan §2-10 + 별도 트랙):
- 피그마 CH4/온도 컬럼 제거 협의 (디자인/프론트)
- `GasTypeChoices.LEL` dead code grep + cleanup (별도 PR)
- IntegrationLog `target_system` 형식 표준화 (Phase 2-e)
- BaseModel 컨벤션 일괄 통일 (Equipment/SafetyCheckItem 외 15개+ 모델)
- 펌웨어 `node_id` 페이로드 변경 (Phase 3-a 선행조건)
- ACTION_GROUP_MAP 그룹핑 코드 (화면 구현 시점)
- Menu.code 형식 ('SNB-01' vs snake_case) — Phase 2-c에서 결정
