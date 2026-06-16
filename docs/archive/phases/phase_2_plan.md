# Phase 2 — 도메인 모델 PR 구현 plan

## Context

[Phase 1 통합 PR](/home/cjy/.claude/plans/verdant-cascading-nebula.md)이 머지된 후, 부모 plan [swirling-mixing-torvalds.md](/home/cjy/.claude/plans/swirling-mixing-torvalds.md) §3 의존 그래프의 **[Phase 2 — 도메인 모델 PR]** 8건을 단일 PR로 묶어 진행한다.

Phase 1이 코드 이넘·기반 모델·신규 앱(operations/reference)을 깔았으므로, Phase 2는 그 위에 도메인 모델을 쌓는다. AlertPolicy ↔ HazardType 매핑, AppLog/IntegrationLog 운영 로그, Threshold DB화, Menu DB화 + dashboard 전환, Notice/VRTraining 신규 도메인 앱 등.

본 PR도 **모델·이넘·마이그레이션·시드·어드민 위주**이며, 화면 서비스(policy_matcher/template_renderer/메뉴 트리 DB 조회 전환)는 Phase 4로 분리. 단 Phase 2-e의 IntegrationLog는 DRF internal API + fastapi 호출 코드 갱신이 필수 동반(쓰는 쪽 코드가 함께 들어가야 의미 있음).

---

## 0. 사용자 결정 사항 (확정 ✅)

| 항목 | 결정 |
|---|---|
| 진행 단위 | **단일 PR/commit** (Phase 1과 동일) |
| Menu.code 형식 | **snake_case** (`dashboard_main`, `equipment_management` 등) |
| VRTrainingContent UNIQUE | **부분 UniqueConstraint** (`is_active=True`일 때만) — PostgreSQL 부분 인덱스 |
| Notice 첨부 제약 | **최대 10MB, 이미지+문서** (jpg/png/gif/pdf/docx/xlsx/pptx) |

추가 결정 항목 (PR 진행 중 합의 후 본 plan §0에 갱신):

### 0-5. HazardType seed 매핑 (필수)

`HazardType.type_code`는 `AlarmType` 10종과 1:1 일치. seed에 들어갈 메타(이름·그룹·색상·표시 우선순위)는 본 PR 진행 중 1차 안 작성 후 사용자 확인.

기본 매핑:
| type_code | 그룹 | 표시명 | RiskLevel 매핑 |
|---|---|---|---|
| `gas_threshold` | 환경 위험 | 가스 경보 | warning/danger (수치 기반) |
| `power_overload` | 설비 위험 | 전력 이상 | warning/danger |
| `geofence_intrusion` | 위치 위험 | 위험구역 진입 | danger |
| `sensor_fault` | 시스템 | 센서 이상 | warning |
| `ppe_violation` | 작업자 위험 | PPE 미착용 | warning/danger |
| `vr_training_not_done` | 작업자 위험 | VR 교육 미이수 | warning |
| `safety_check_pending` | 작업자 위험 | 체크리스트 미완료 | warning |
| `inspection_scheduled` | 운영 일정 | 점검 예정 | normal/warning |
| `batch_failed` | 시스템 | 배치 실패 | warning |
| `storage_overdue` | 운영 일정 | 보관 주기 실패 | warning |

5개 그룹: 환경 위험 / 설비 위험 / 위치 위험 / 작업자 위험 / 운영 일정 / 시스템.

### 0-6. IntegrationLog `target_system` 식별자 표준화

부모 plan §2-10 후속 항목. 본 PR에서 형식 규약 1차 확정:

```
"<source>→<destination>"        # 시스템 간 호출, 예: "FastAPI→DRF"
"<system>:<resource_id>"        # 단일 시스템 + 리소스, 예: "GasSensor:GS-001", "SMS:NCloud"
```

자유 텍스트로 보존하되 화면 필터 효율을 위해 위 두 패턴을 운영 컨벤션으로 명시 (constants에는 docstring/예시만, 강제 validator는 없음).

### 0-7. AppLog 활성화 범위

`logger.error()` 이상만 DBLogHandler로 영속화. INFO/DEBUG는 stdout만. 재귀 가드 + 비동기 처리(Celery 또는 메모리 큐)는 Phase 2-d 작업 시 결정.

본 PR에서는 **모델 + DBLogHandler 골격까지만**. 비동기 처리·재귀 가드 운영은 Phase 4-c 화면 구현과 함께 운영 부하 측정 후 튜닝.

---

## 1. 작업 범위 — Phase 2 PR에 포함되는 항목 (8건)

| # | 작업 | 영향 |
|---|---|---|
| 2a | `HazardTypeGroup` + `HazardType` (alerts) + seed 10 row + AlarmType↔HazardType CI 활성화 | alerts/models, alerts/migrations, alerts/admin, alerts/tests |
| 2b | `ThresholdGroup` + `Threshold` (facilities) | facilities/models/thresholds.py(빈 파일 활용), migrations, admin |
| 2c | `Menu` + `RoleMenuVisibility` (dashboard) + 기존 menu.py 데이터 마이그레이션 | dashboard/models/* (신규), migrations, admin |
| 2d | `AppLog` (operations) + DBLogHandler 골격 | operations/models, operations/logging/db_handler.py, settings.LOGGING |
| 2e | `IntegrationLog` (operations) + DRF internal API + drf_client/alerts.tasks/notifications 3곳 호출 갱신 | operations/models, drf-server urls + view, fastapi-server drf_client.py, alerts/tasks.py, notifications |
| 2f | `AlertPolicy` (alerts) + target_user_types JSON | alerts/models, alerts/migrations, alerts/admin |
| 2g | `apps/notices` 신설 (Notice + NoticeAttachment) | 신규 앱 |
| 2h | `apps/training` 신설 (VRTrainingContent + VRTrainingRevision) | 신규 앱 |

---

## 2. 작업 상세

### 2a. HazardTypeGroup + HazardType (alerts)

**신설 파일:**
- `drf-server/apps/alerts/models/hazard_type_group.py`
- `drf-server/apps/alerts/models/hazard_type.py`
- `drf-server/apps/alerts/fixtures/hazard_type.json` (5 group + 10 type)
- `drf-server/apps/alerts/migrations/000X_hazard_type.py`
- `drf-server/apps/alerts/migrations/000X_seed_hazard_type.py` (RunPython loaddata)
- `drf-server/apps/alerts/tests/test_alarm_type_consistency.py`

**스키마:**
```python
class HazardTypeGroup(BaseModel):
    code = CharField(max_length=50, unique=True)         # environment/equipment/location/worker/operation/system
    name = CharField(max_length=100)                      # 환경 위험/설비 위험/...
    sort_order = PositiveIntegerField(default=0)
    is_active = BooleanField(default=True)

class HazardType(BaseModel):
    group = ForeignKey(HazardTypeGroup, on_delete=PROTECT, related_name="types")
    type_code = CharField(max_length=50, unique=True)    # AlarmType.values와 1:1
    name = CharField(max_length=100)                      # "가스 경보" 등
    display_color = CharField(max_length=20, default="orange")
    map_visible = BooleanField(default=True)
    description = TextField(blank=True, default="")
    is_active = BooleanField(default=True)

    class Meta:
        constraints = [UniqueConstraint(fields=["type_code"], name="uq_hazard_type_code")]
```

**alerts/models/__init__.py 갱신:** 두 모델 re-export.

**CI 정합성 테스트 활성화 (alerts/tests/test_alarm_type_consistency.py):**
```python
class AlarmTypeConsistencyTest(TestCase):
    fixtures = ["hazard_type"]

    def test_alarm_type_enum_matches_hazard_type(self):
        db_codes = set(HazardType.objects.filter(is_active=True)
                                          .values_list("type_code", flat=True))
        enum_codes = set(AlarmType.values)
        only_in_enum = enum_codes - db_codes
        only_in_db = db_codes - enum_codes
        self.assertFalse(
            only_in_enum or only_in_db,
            f"AlarmType ↔ HazardType 불일치:\n"
            f"  enum-only: {only_in_enum}\n"
            f"  db-only:   {only_in_db}",
        )
```

---

### 2b. ThresholdGroup + Threshold (facilities)

**대상 파일:** [drf-server/apps/facilities/models/thresholds.py](drf-server/apps/facilities/models/thresholds.py) (현재 빈 파일, 4차 예고 주석 존재)

**스키마:**
```python
class ThresholdGroup(BaseModel):
    code = CharField(max_length=50, unique=True)         # gas_legal, gas_facility_default, power_default
    name = CharField(max_length=100)
    description = TextField(blank=True, default="")
    is_active = BooleanField(default=True)

class Threshold(BaseModel):
    group = ForeignKey(ThresholdGroup, on_delete=PROTECT, related_name="thresholds")
    measurement_item = CharField(max_length=50)           # co/h2s/.../power_w (CharField + 검색 컨벤션)
    warning_min = DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    warning_max = DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    danger_min = DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    danger_max = DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    unit = CharField(max_length=10, default="ppm")
    description = TextField(blank=True, default="")
    is_active = BooleanField(default=True)

    class Meta:
        constraints = [UniqueConstraint(fields=["group", "measurement_item"],
                                         name="uq_threshold_group_item")]
```

**Phase 2에서 신설은 모델만**. `power_alarm.py`/`gas_data.py risk 계산` DB 조회 전환은 Phase 4-b/4-c. 따라서 본 PR은 시드 데이터 0 (또는 최소 1건만 demo).

부모 plan §1-2의 imsi 권고대로 `Threshold.measurement_item`은 CharField 유지 + validator로 `[a-z][a-z0-9_]*` 패턴 강제.

---

### 2c. Menu + RoleMenuVisibility (dashboard)

**신설 디렉토리:** `drf-server/apps/dashboard/models/` (현재 dashboard 앱은 menu.py 하드코딩만 있음 — models 디렉토리 신규)

**스키마:**
```python
class Menu(BaseModel):
    code = CharField(max_length=50, unique=True)         # snake_case (dashboard_main, equipment_management)
    name = CharField(max_length=100)                      # 화면 표시명
    parent = ForeignKey("self", on_delete=CASCADE, null=True, blank=True, related_name="children")
    menu_type = CharField(max_length=20, choices=[
        ("snb", "사이드바"),
        ("admin", "어드민"),
    ])
    sort_order = PositiveIntegerField(default=0)
    icon = CharField(max_length=50, blank=True, default="")
    url_path = CharField(max_length=200, blank=True, default="")
    is_active = BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "code"]

class RoleMenuVisibility(BaseModel):
    role_profile = ForeignKey("accounts.RoleProfile", on_delete=CASCADE, related_name="menu_visibilities")
    menu = ForeignKey(Menu, on_delete=CASCADE, related_name="role_visibilities")
    is_visible = BooleanField(default=True)

    class Meta:
        constraints = [UniqueConstraint(fields=["role_profile", "menu"], name="uq_rolemenu")]
```

**기존 dashboard/menu.py 데이터 마이그레이션:** 하드코딩된 `_MENU_WORKER`, `_MENU_ADMIN_EXTRA`를 Menu seed로 변환. RunPython으로 작성.

**Phase 2에서는 모델 + 시드만**. `dashboard/views.py`의 `get_menu_tree(role)` DB 조회 전환은 Phase 4-a.

---

### 2d. AppLog + DBLogHandler 골격 (operations)

**신설 파일:**
- `drf-server/apps/operations/models/app_log.py`
- `drf-server/apps/operations/logging/db_handler.py`
- `drf-server/apps/operations/migrations/000X_app_log.py`

**스키마:**
```python
class AppLog(models.Model):  # BaseModel 미상속 — actor 없는 운영 로그, APPEND-ONLY
    class LogCategory(TextChoices):
        ERROR = "error", "오류"
        BATCH = "batch", "배치"
        SERVICE = "service", "서비스"

    log_category = CharField(max_length=20, choices=LogCategory.choices)
    service_module = CharField(max_length=100)            # "celery.tasks.fire_alarm"
    level = CharField(max_length=10)                      # ERROR/WARN/INFO
    message = TextField()
    extra = JSONField(null=True, blank=True)
    created_at = DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("AppLog는 수정할 수 없습니다. APPEND-ONLY 정책.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AppLog는 삭제할 수 없습니다.")

    class Meta:
        db_table = "app_log"
        indexes = [
            Index(fields=["log_category", "-created_at"]),
            Index(fields=["-created_at"]),
        ]
```

**DBLogHandler (operations/logging/db_handler.py):**
```python
import logging
from threading import local

class DBLogHandler(logging.Handler):
    """
    logger.error() 등을 AppLog 테이블에 영속화.
    재귀 가드: 핸들러 자체에서 발생한 예외는 stdout만 (무한 루프 회피).
    """
    _guard = local()

    def emit(self, record):
        if getattr(self._guard, "active", False):
            return
        self._guard.active = True
        try:
            from apps.operations.models import AppLog
            AppLog.objects.create(
                log_category=self._infer_category(record),
                service_module=record.name,
                level=record.levelname,
                message=self.format(record),
            )
        except Exception:
            pass  # 재귀/DB 오류 시 silent. stdout 핸들러가 백업.
        finally:
            self._guard.active = False

    @staticmethod
    def _infer_category(record):
        if "celery" in record.name or "batch" in record.name:
            return "batch"
        return "error" if record.levelno >= logging.ERROR else "service"
```

**settings.LOGGING 확장:** `DBLogHandler`를 `handlers`에 추가, root logger에 연결. **Phase 2에서는 ERROR 이상만 캡처 (level="ERROR")**.

**비동기 처리(Celery 큐 또는 thread-pool)는 Phase 4** — 본 PR에서는 동기 INSERT. 운영 트래픽 중 INSERT 부담 측정은 Phase 4 화면 구현 시점에 결정.

---

### 2e. IntegrationLog (operations) + DRF internal API + 호출 코드 갱신

**신설 파일:**
- `drf-server/apps/operations/models/integration_log.py`
- `drf-server/apps/operations/views/internal/integration_log.py`
- `drf-server/apps/operations/urls.py` (신규)
- `drf-server/apps/operations/serializers/integration_log.py`

**스키마:**
```python
class IntegrationLog(models.Model):  # APPEND-ONLY
    class IntegrationType(TextChoices):
        COLLECT = "collect", "수집"
        TRANSMIT = "transmit", "전송"
        SYNC = "sync", "동기화"
    class Result(TextChoices):
        SUCCESS = "success", "성공"
        FAILURE = "failure", "실패"
        DELAY = "delay", "지연"

    integration_type = CharField(max_length=20, choices=IntegrationType.choices)
    target_system = CharField(max_length=100)             # "FastAPI→DRF" / "GasSensor:GS-001"
    result = CharField(max_length=10, choices=Result.choices)
    description = TextField(blank=True, default="")
    extra = JSONField(null=True, blank=True)
    created_at = DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("IntegrationLog는 APPEND-ONLY")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("IntegrationLog는 삭제할 수 없습니다.")

    class Meta:
        db_table = "integration_log"
        indexes = [
            Index(fields=["integration_type", "-created_at"]),
            Index(fields=["result", "-created_at"]),
            Index(fields=["-created_at"]),
        ]
```

**DRF internal API:**
- URL: `POST /api/internal/integration-logs/`
- 권한: localhost-only IP 화이트리스트 미들웨어 또는 view 단 검증 (alarm_router 패턴 차용)
- 인증: 별도 미들웨어 (JWT 우회 — internal-only)

**기록 지점 3곳:**
1. **fastapi-server `services/drf_client.py`**의 `post_to_drf()`: 호출 후 `_record_integration_log(integration_type=...)` 호출. fire-and-forget(`raise_on_error=False`).
2. **drf-server `apps/alerts/tasks.py`**의 `_push_to_ws()`: ORM 직접 `IntegrationLog.objects.create(...)`.
3. **drf-server `apps/notifications/`** 발송 후: ORM 직접.

**부하 완화:** 부모 plan §2-8 결정대로 fire-and-forget으로 시작. batch flush는 Phase 4 운영 부하 측정 후.

**target_system 형식:** `"FastAPI→DRF"` / `"GasSensor:GS-001"` 패턴 (§0-6).

---

### 2f. AlertPolicy (alerts) + target_user_types JSON

**신설 파일:** `drf-server/apps/alerts/models/alert_policy.py`

**스키마 (CJY plan + 부모 plan §2-4 결정 반영):**
```python
class AlertPolicy(BaseModel):
    class PolicyKind(TextChoices):
        STATEFUL = "stateful", "상태 기반"      # 가스 임계치 등
        IMMEDIATE = "immediate", "즉시"          # PPE 미착용 등
        SCHEDULED = "scheduled", "예정"          # 점검 일정 등

    name = CharField(max_length=100)
    event_type = CharField(max_length=50, choices=AlarmType.choices)  # USER_FACING_ALARM_TYPES 기반
    policy_kind = CharField(max_length=20, choices=PolicyKind.choices)
    target_facility = ForeignKey("facilities.Facility", on_delete=CASCADE,
                                  null=True, blank=True,
                                  help_text="NULL이면 전사 정책")
    target_user_types = JSONField(default=list,
                                   help_text='lowercase user_type 배열, 예: ["facility_admin", "worker"]')
    target_sensor_ids = JSONField(default=list, blank=True)
    target_device_ids = JSONField(default=list, blank=True)
    target_geofence_ids = JSONField(default=list, blank=True)
    channels = JSONField(default=list,
                          help_text='Notification.Channel.values 부분집합, 예: ["popup", "sms"]')
    condition_summary = CharField(max_length=300, blank=True, default="",
                                   help_text="목록 화면 캐시 — service 레이어에서 갱신")
    is_active = BooleanField(default=True)
    description = TextField(blank=True, default="")

    class Meta:
        indexes = [
            Index(fields=["event_type", "is_active"]),
            Index(fields=["target_facility", "is_active"]),
        ]
```

**Phase 2-f는 모델만**. `policy_matcher` 서비스 + condition_summary 자동 갱신은 Phase 4-e.

---

### 2g. apps/notices 신설

**신설 디렉토리:** `drf-server/apps/notices/`

**모델:**
```python
class Notice(BaseModel):
    class Category(TextChoices):
        GENERAL = "general", "일반 공지"
        URGENT = "urgent", "긴급 공지"
        MAINTENANCE = "maintenance", "점검 안내"

    title = CharField(max_length=200)
    content = TextField()
    category = CharField(max_length=20, choices=Category.choices, default=Category.GENERAL)
    author = ForeignKey(settings.AUTH_USER_MODEL, on_delete=SET_NULL, null=True, blank=True,
                         related_name="notices_authored")
    is_pinned = BooleanField(default=False)
    target_facility = ForeignKey("facilities.Facility", on_delete=CASCADE, null=True, blank=True,
                                  help_text="NULL이면 전사 공지")
    is_active = BooleanField(default=True)
    published_at = DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            Index(fields=["-is_pinned", "-published_at"]),
            Index(fields=["category", "-published_at"]),
        ]

class NoticeAttachment(BaseModel):
    notice = ForeignKey(Notice, on_delete=CASCADE, related_name="attachments")
    file = FileField(upload_to=notice_attachment_path,
                      validators=[validate_max_10mb, validate_allowed_extension])
    filename = CharField(max_length=200)  # 원본 파일명 보존
    size = PositiveIntegerField()
```

**validators (apps/notices/validators.py — Phase 2 한정, 향후 다른 첨부 도메인 등장 시 core/validators.py로 이동):**
```python
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "pdf", "docx", "xlsx", "pptx"}

def validate_max_10mb(file):
    if file.size > 10 * 1024 * 1024:
        raise ValidationError("첨부파일은 10MB를 초과할 수 없습니다.")

def validate_allowed_extension(file):
    ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"허용되지 않은 확장자: {ext}. 허용: {ALLOWED_EXTENSIONS}")
```

**ActionType:** Phase 1에서 이미 `NOTICE_CREATE/UPDATE/DELETE` 추가됨 → 화면 구현 시점에 SystemLog 기록 코드 추가 (Phase 4 외).

---

### 2h. apps/training 신설

**신설 디렉토리:** `drf-server/apps/training/`

**모델:**
```python
class VRTrainingContent(BaseModel):
    class TargetType(TextChoices):
        GAS_SENSOR = "gas_sensor", "가스 센서"
        GENERAL = "general", "일반"

    target_type = CharField(max_length=20, choices=TargetType.choices)
    target_facility = ForeignKey("facilities.Facility", on_delete=CASCADE, null=True, blank=True,
                                  help_text="NULL이면 전사 콘텐츠")
    name = CharField(max_length=200)
    content_url = URLField(max_length=500)
    description = TextField(blank=True, default="")
    is_active = BooleanField(default=True)

    class Meta:
        constraints = [
            # 부분 UniqueConstraint: is_active=True일 때만 (target_type, target_facility) 1개
            UniqueConstraint(
                fields=["target_type", "target_facility"],
                condition=Q(is_active=True),
                name="uq_vr_active_target",
            ),
        ]

class VRTrainingRevision(BaseModel):
    """교체 이력 — VRTrainingContent 교체 시 이전 버전 스냅샷 보존."""
    content = ForeignKey(VRTrainingContent, on_delete=CASCADE, related_name="revisions")
    previous_url = URLField(max_length=500)
    previous_name = CharField(max_length=200)
    replaced_at = DateTimeField(auto_now_add=True)
    replaced_by = ForeignKey(settings.AUTH_USER_MODEL, on_delete=SET_NULL, null=True, blank=True)
    reason = TextField(blank=True, default="")

    class Meta:
        indexes = [Index(fields=["content", "-replaced_at"])]
```

**ActionType:** Phase 1에서 `VR_CONTENT_CREATED/REPLACED/TOGGLED` 이미 추가 — 화면 구현 시점에 SystemLog 기록 (Phase 4 외).

---

## 3. 마이그레이션 순서 (단일 PR 내 자동 정렬)

Django는 의존성 따라 자동 정렬. 수동 순서 강제 불필요.

신규 마이그레이션:
- `accounts/000X_alter_roleprofile_*` (필요 시)
- `alerts/000X_hazardtypegroup_hazardtype_alertpolicy.py`
- `alerts/000X_seed_hazard_type.py` (RunPython loaddata)
- `dashboard/0001_initial.py` (Menu, RoleMenuVisibility — 현재 dashboard 앱은 migrations 디렉토리만 존재)
- `dashboard/0002_seed_menu.py` (RunPython, 기존 menu.py 하드코딩 변환)
- `facilities/000X_thresholdgroup_threshold.py`
- `notices/0001_initial.py`
- `operations/000X_app_log_integration_log.py`
- `training/0001_initial.py`

---

## 4. 검증 방법

### 4-1. 빌드 / 스키마
```bash
cd drf-server
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --dry-run --check
.venv/bin/python manage.py migrate
```

### 4-2. 시드 데이터
```bash
.venv/bin/python manage.py shell -c "
from apps.alerts.models import HazardType
from apps.dashboard.models import Menu
print('HazardType:', list(HazardType.objects.values_list('type_code', flat=True)))
print('Menu:', list(Menu.objects.values_list('code', flat=True)))
"
```

### 4-3. CI 정합성 테스트 (3종 모두 활성)
```bash
.venv/bin/python manage.py test \
  apps.reference.tests.test_gas_type_consistency \
  apps.core.tests.test_risk_level_standard_consistency \
  apps.alerts.tests.test_alarm_type_consistency
```
기대: 모두 OK.

### 4-4. IntegrationLog internal API 통합 테스트
```bash
# DRF + FastAPI 동시 기동 후
curl -X POST http://127.0.0.1:8000/api/internal/integration-logs/ \
  -H "Content-Type: application/json" \
  -d '{"integration_type":"transmit","target_system":"FastAPI→DRF","result":"success"}'
# → 200 + IntegrationLog 1 row 생성 확인
```

### 4-5. ruff / pre-commit
```bash
pre-commit run --files <변경파일>
```

### 4-6. AppLog DBLogHandler 회귀
```python
import logging
logger = logging.getLogger("apps.alerts.test")
logger.error("test message")
# → AppLog 1 row 생성 확인
```

---

## 5. Critical Files (PR 변경 대상)

**신규 디렉토리:**
- `drf-server/apps/notices/`
- `drf-server/apps/training/`
- `drf-server/apps/dashboard/models/`
- `drf-server/apps/operations/logging/`
- `drf-server/apps/operations/views/internal/`

**신규 파일 (모델/마이그레이션/fixture/admin/views/test):**
- 8개 작업 항목 각각의 모델 + 어드민 + 시드 마이그레이션 + 적용 시 정합성 테스트

**수정 파일:**
- [drf-server/config/settings.py](drf-server/config/settings.py) — INSTALLED_APPS에 `apps.notices`, `apps.training` 추가, LOGGING에 DBLogHandler
- [drf-server/config/urls.py](drf-server/config/urls.py) — `/api/internal/integration-logs/` 라우터 등록
- [drf-server/apps/alerts/models/__init__.py](drf-server/apps/alerts/models/) — HazardType + AlertPolicy re-export
- [drf-server/apps/alerts/tasks.py](drf-server/apps/alerts/tasks.py) — `_push_to_ws` 마지막에 IntegrationLog.objects.create(...)
- [drf-server/apps/dashboard/](drf-server/apps/dashboard/) — apps.py, models, migrations 디렉토리 신설 (현재 menu.py + views.py만)
- [drf-server/apps/facilities/models/thresholds.py](drf-server/apps/facilities/models/thresholds.py) — 빈 파일 → 모델 작성
- [drf-server/apps/operations/](drf-server/apps/operations/) — models 추가, logging/db_handler.py 추가, views/internal/, urls.py
- [fastapi-server/services/drf_client.py](fastapi-server/services/drf_client.py) — IntegrationLog 호출 추가

---

## 6. 실행 체크리스트

- [ ] 2a: HazardTypeGroup + HazardType 모델 + fixture (5 group + 10 type) + RunPython seed + AlarmType↔HazardType CI 테스트 활성화
- [ ] 2b: ThresholdGroup + Threshold 모델 (시드 없음, Phase 4-c 진입 전 결정)
- [ ] 2c: Menu + RoleMenuVisibility 모델 + 기존 menu.py 데이터 마이그레이션 (snake_case 코드)
- [ ] 2d: AppLog 모델 + DBLogHandler + settings.LOGGING 확장 (ERROR level만)
- [ ] 2e: IntegrationLog 모델 + DRF internal API + 3곳 호출 코드 갱신 (drf_client/alerts/notifications)
- [ ] 2f: AlertPolicy 모델 (target_user_types JSON, USER_FACING_ALARM_TYPES choices)
- [ ] 2g: apps/notices 앱 신설 (Notice + NoticeAttachment + 첨부 validator)
- [ ] 2h: apps/training 앱 신설 (VRTrainingContent + Revision, 부분 UniqueConstraint)
- [ ] settings.py INSTALLED_APPS에 notices/training 추가
- [ ] 어드민 등록 (각 신규 모델)
- [ ] makemigrations + migrate 클린 적용
- [ ] CI 정합성 테스트 3종 모두 OK
- [ ] pre-commit 통과
- [ ] Phase 2 보고서 작성 + commit

---

## 7. 미해결 / Phase 2 외 항목

본 PR 범위 외 후속:
- Phase 3-a: WorkerPosition.received_node FK + 펌웨어 동기
- Phase 3-b: SafetyCheckSection + SafetyCheckItem.section FK
- Phase 3-c: SafetyChecklistRevision + SafetyCheckSession + SafetyStatus UNIQUE 변경
- Phase 3-d: Event 확장 (policy FK, description, status_note)
- Phase 3-e: Notification 확장 (policy FK, retry_count, last_attempted_at, event SET_NULL)
- Phase 4-a: dashboard 메뉴 DB 조회 전환 (get_menu_tree)
- Phase 4-b: power_alarm.py DB Threshold 조회
- Phase 4-c: gas_data risk 계산 DB 기반 + 캐시
- Phase 4-d: threshold_service.py 재작성
- Phase 4-e: AlertPolicy policy_matcher 서비스 + condition_summary 자동 갱신
- Phase 4-f: Notification template_renderer 서비스
- Phase 4-g: DataRetentionPolicy Celery 보관 배치
- AppLog 비동기 처리 / 재귀 가드 운영 튜닝
- IntegrationLog batch flush 전환 (운영 부하 측정 후)
