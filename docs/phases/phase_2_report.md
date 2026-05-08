# Phase 2 — 도메인 모델 PR 보고서

> 작업일: 2026-05-08
> 브랜치: `feature/0508_refactory`
> 부모 plan: [.claude/plans/swirling-mixing-torvalds.md](../../.claude/plans/swirling-mixing-torvalds.md)
> 구현 plan: [phase_2_plan.md](phase_2_plan.md)
> 직전 Phase: [phase_1_report.md](phase_1_report.md)

---

## 1. 작업 목적

[Phase 1](phase_1_report.md)에서 깐 기반(코드 이넘·기반 모델·신규 앱 operations/reference)을 토대로, 부모 plan §3 의존 그래프 [Phase 2 — 도메인 모델 PR] 8건을 단일 PR로 묶어 진행.

| Sub-step | 작업 | 앱 |
|---|---|---|
| 2a | HazardTypeGroup + HazardType + seed + AlarmType↔HazardType CI | alerts |
| 2b | ThresholdGroup + Threshold | facilities |
| 2c | Menu + RoleMenuVisibility + 기존 menu.py 시드 변환 | dashboard |
| 2d | AppLog + DBLogHandler + LOGGING settings | operations |
| 2e | IntegrationLog + DRF internal API + drf_client/alerts.tasks 호출 갱신 | operations + fastapi |
| 2f | AlertPolicy | alerts |
| 2g | apps/notices 신설 (Notice + NoticeAttachment) | (신규) |
| 2h | apps/training 신설 (VRTrainingContent + VRTrainingRevision) | (신규) |

본 PR은 **모델·이넘·마이그레이션·시드·어드민·로그 기록 위주**. 화면 서비스(policy_matcher/template_renderer/메뉴 트리 DB 조회 전환)는 Phase 4로 분리. Phase 2-e 한정으로 IntegrationLog 호출 코드(쓰는 쪽)가 함께 들어감 — 모델만 만들어두면 의미 없음.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `python manage.py check` | ✅ 통과 |
| 마이그레이션 일관성 | `python manage.py makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그레이션 적용 | `python manage.py migrate` | ✅ 모든 마이그레이션 적용 + HazardType 16 row + Menu 12 row 시드 |
| CI 정합성 테스트 | `python manage.py test apps.reference.tests... apps.core.tests... apps.alerts.tests.test_alarm_type_consistency` | ✅ 4 tests OK |
| ruff lint + format | `pre-commit run --files <변경파일>` | ✅ Passed |

### 시드 데이터

```python
HazardTypeGroup: ['environment', 'equipment', 'location', 'worker', 'operation', 'system']
HazardType: ['gas_threshold', 'power_overload', 'geofence_intrusion', 'ppe_violation',
             'safety_check_pending', 'vr_training_not_done', 'inspection_scheduled',
             'storage_overdue', 'batch_failed', 'sensor_fault']  # AlarmType 10종 1:1
Menu count: 12 (snake_case 변환 완료)
```

### CI 정합성 테스트 4종 모두 통과

- ✅ `test_gas_type_enum_matches_common_code` (Phase 1)
- ✅ `test_enum_matches_db` — RiskLevel ↔ RiskLevelStandard (Phase 1)
- ✅ `test_priority_unique` — RiskLevelStandard.event_priority (Phase 1)
- ✅ `test_alarm_type_enum_matches_hazard_type` — **Phase 2 신규 활성화**

---

## 3. 변경 파일 — 신규 (역할별)

### 3-1. 신규 앱 디렉토리 (2개)

| 경로 | 역할 |
|---|---|
| [drf-server/apps/notices/](../../drf-server/apps/notices/) | 공지사항 게시물 (Notice + NoticeAttachment + validators) |
| [drf-server/apps/training/](../../drf-server/apps/training/) | VR 교육 콘텐츠 (VRTrainingContent + VRTrainingRevision 교체 이력) |

각 앱: `__init__.py`, `apps.py`, `admin.py`, `models/`, `migrations/`, `tests/`.

### 3-2. 신규 모델 파일 (12개)

| 파일 | 모델 | 역할 |
|---|---|---|
| [alerts/models/hazard_type_group.py](../../drf-server/apps/alerts/models/hazard_type_group.py) | `HazardTypeGroup` | 위험 유형 그룹 마스터 (환경/설비/위치/작업자/운영/시스템) |
| [alerts/models/hazard_type.py](../../drf-server/apps/alerts/models/hazard_type.py) | `HazardType` | AlarmType 이넘과 1:1 매핑 마스터 (UI 편집용) |
| [alerts/models/alert_policy.py](../../drf-server/apps/alerts/models/alert_policy.py) | `AlertPolicy` | "어떤 이벤트 → 누구에게 어떤 채널" 정책. target_user_types JSON 시작 |
| [facilities/models/thresholds.py](../../drf-server/apps/facilities/models/thresholds.py) | `ThresholdGroup`, `Threshold` | 임계치 DB화 — 기존 빈 파일 → 모델 작성 |
| [dashboard/models/menu.py](../../drf-server/apps/dashboard/models/menu.py) | `Menu` | 메뉴 마스터 (parent self-FK, snake_case 코드) |
| [dashboard/models/role_menu_visibility.py](../../drf-server/apps/dashboard/models/role_menu_visibility.py) | `RoleMenuVisibility` | RoleProfile × Menu 노출 매핑 |
| [operations/models/app_log.py](../../drf-server/apps/operations/models/app_log.py) | `AppLog` | 운영 로그 (logger.error 등 영속화). APPEND-ONLY |
| [operations/models/integration_log.py](../../drf-server/apps/operations/models/integration_log.py) | `IntegrationLog` | 시스템 간 호출 영속화. APPEND-ONLY |
| [notices/models/notice.py](../../drf-server/apps/notices/models/notice.py) | `Notice` | 공지사항 (category/is_pinned/target_facility) |
| [notices/models/notice_attachment.py](../../drf-server/apps/notices/models/notice_attachment.py) | `NoticeAttachment` | 첨부파일 (10MB, 8종 확장자 validator) |
| [training/models/vr_training_content.py](../../drf-server/apps/training/models/vr_training_content.py) | `VRTrainingContent` | VR 교육 콘텐츠. 부분 UniqueConstraint(is_active=True) |
| [training/models/vr_training_revision.py](../../drf-server/apps/training/models/vr_training_revision.py) | `VRTrainingRevision` | 콘텐츠 교체 이력 스냅샷 |

### 3-3. 인프라 코드 신규 (5개)

| 파일 | 역할 |
|---|---|
| [operations/logging/db_handler.py](../../drf-server/apps/operations/logging/db_handler.py) | `DBLogHandler` — Python logging → AppLog 영속화. 재귀 가드 thread-local |
| [operations/views/internal/integration_log.py](../../drf-server/apps/operations/views/internal/integration_log.py) | `IntegrationLogInternalCreateView` — `POST /api/internal/integration-logs/`. localhost-only IP 화이트리스트 + JWT 우회 |
| [operations/serializers/integration_log.py](../../drf-server/apps/operations/serializers/integration_log.py) | DRF serializer for IntegrationLog |
| [operations/urls.py](../../drf-server/apps/operations/urls.py) | operations 앱 URL (internal-integration-log-create) |
| [notices/validators.py](../../drf-server/apps/notices/validators.py) | `validate_max_10mb`, `validate_allowed_extension` (jpg/png/gif/pdf/docx/xlsx/pptx) |

### 3-4. fixture (2개)

| 파일 | 시드 내용 |
|---|---|
| [alerts/fixtures/hazard_type.json](../../drf-server/apps/alerts/fixtures/hazard_type.json) | HazardTypeGroup 6 row + HazardType 10 row (AlarmType 10종 1:1) |
| [dashboard/fixtures/menu.json](../../drf-server/apps/dashboard/fixtures/menu.json) | Menu 12 row (snake_case 변환, parent FK 포함) |

### 3-5. 마이그레이션 (8개)

| 파일 | 역할 |
|---|---|
| `alerts/0004_hazardtypegroup_hazardtype_alertpolicy.py` | 3개 모델 생성 |
| `alerts/0005_seed_hazard_type.py` | RunPython으로 fixture 자동 로드 |
| `dashboard/0001_initial.py` | Menu + RoleMenuVisibility 생성 (dashboard 앱 첫 마이그레이션) |
| `dashboard/0002_seed_menu.py` | RunPython 메뉴 12 row 시드 |
| `facilities/0010_thresholdgroup_threshold.py` | ThresholdGroup + Threshold 생성 |
| `notices/0001_initial.py` | Notice + NoticeAttachment 생성 |
| `operations/0002_applog_integrationlog.py` | AppLog + IntegrationLog 생성 |
| `training/0001_initial.py` | VRTrainingContent + VRTrainingRevision 생성 (부분 UniqueConstraint 포함) |

### 3-6. CI 정합성 테스트 (1개)

| 파일 | 검증 |
|---|---|
| [alerts/tests/test_alarm_type_consistency.py](../../drf-server/apps/alerts/tests/test_alarm_type_consistency.py) | `AlarmType` 10종 ↔ `HazardType.type_code` 1:1 일치 |

---

## 4. 변경 파일 — 기존 수정

### 4-1. 설정 / 라우팅

| 파일 | 변경 내용 |
|---|---|
| [config/settings.py](../../drf-server/config/settings.py) | `INSTALLED_APPS`에 `apps.notices`, `apps.training` 추가. `LOGGING.handlers`에 `applog_db` (DBLogHandler, level=ERROR) 추가, root logger에 연결 |
| [config/urls.py](../../drf-server/config/urls.py) | `path("api/", include("apps.operations.urls"))` 추가 → `/api/internal/integration-logs/` 진입 |

### 4-2. 모델 모듈 인덱스

| 파일 | 변경 내용 |
|---|---|
| [alerts/models/__init__.py](../../drf-server/apps/alerts/models/__init__.py) | `HazardType`, `HazardTypeGroup`, `AlertPolicy` re-export |
| [facilities/models/__init__.py](../../drf-server/apps/facilities/models/__init__.py) | `Threshold`, `ThresholdGroup` re-export. 기존 4차 예고 주석 제거 |
| [operations/models/__init__.py](../../drf-server/apps/operations/models/__init__.py) | `AppLog`, `IntegrationLog` re-export 추가 |

### 4-3. 어드민 등록

| 파일 | 등록한 모델 |
|---|---|
| [alerts/admin.py](../../drf-server/apps/alerts/admin.py) | `HazardTypeGroup`, `HazardType` (`type_code` readonly), `AlertPolicy` |
| [facilities/admin.py](../../drf-server/apps/facilities/admin.py) | `ThresholdGroup`, `Threshold` |
| [dashboard/admin.py](../../drf-server/apps/dashboard/admin.py) (신규) | `Menu`, `RoleMenuVisibility` |
| [operations/admin.py](../../drf-server/apps/operations/admin.py) | `AppLog`, `IntegrationLog` (둘 다 readonly + has_*_permission False — APPEND-ONLY 강제) |
| [notices/admin.py](../../drf-server/apps/notices/admin.py) (신규) | `Notice` (NoticeAttachment inline), `NoticeAttachment` |
| [training/admin.py](../../drf-server/apps/training/admin.py) (신규) | `VRTrainingContent`, `VRTrainingRevision` |

### 4-4. IntegrationLog 호출 코드 갱신 (Phase 2-e 핵심)

| 파일 | 변경 내용 |
|---|---|
| [fastapi-server/services/drf_client.py](../../fastapi-server/services/drf_client.py) | `INTEGRATION_LOG_PATH` 상수 + `_record_integration_log()` helper (fire-and-forget 비동기 httpx). `post_to_drf` 끝부분에서 path != INTEGRATION_LOG_PATH일 때 결과 영속화 (재귀 회피) |
| [drf-server/apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py) | `_push_to_ws()`에서 httpx.post 결과(success/failure) → ORM 직접 `IntegrationLog.objects.create(...)`. 기록 실패 silent fail |

---

## 5. 사용자 결정 사항 (Phase 2 진입 전 확정)

부모 plan §0의 결정 + 본 Phase 2 §0 결정사항 모두 본 PR에 반영됨.

### 5-1. 진행 단위
**단일 PR/commit** (Phase 1과 동일).

### 5-2. Menu.code 형식
**snake_case** (`dashboard_main`, `equipment_management` 등). 기존 `'SNB-01'` 하이픈 형식은 fixture 변환 시 폐기. 다른 코드값(CodeGroup.code, RoleProfile.code)과 컨벤션 일관.

### 5-3. VRTrainingContent UNIQUE
**부분 UniqueConstraint** (`is_active=True`일 때만). PostgreSQL 부분 인덱스 활용. 교체 시 기존 row는 `is_active=False`로 보존.

### 5-4. Notice 첨부파일 제약
**최대 10MB, 이미지+문서**: jpg/png/gif/pdf/docx/xlsx/pptx. validators는 `apps/notices/validators.py` (Simplicity First — 두 번째 첨부 도메인 등장 시 core/validators.py로 이동).

### 5-5. HazardType 5+1 그룹 매핑 (§0-5)
| 그룹 코드 | 표시명 | HazardType 5종 |
|---|---|---|
| environment | 환경 위험 | gas_threshold |
| equipment | 설비 위험 | power_overload |
| location | 위치 위험 | geofence_intrusion |
| worker | 작업자 위험 | ppe_violation, vr_training_not_done, safety_check_pending |
| operation | 운영 일정 | inspection_scheduled, storage_overdue |
| system | 시스템 | sensor_fault, batch_failed |

### 5-6. IntegrationLog target_system 형식 (§0-6)
- `"<source>→<destination>"` (시스템 간), 예: `"FastAPI→DRF"`, `"DRF→FastAPI"`
- `"<system>:<resource_id>"` (단일 시스템 + 리소스), 예: `"GasSensor:GS-001"`, `"SMS:NCloud"`
자유 텍스트로 보존하되 위 두 패턴을 운영 컨벤션으로 docstring에 명시 (validator 강제는 안 함).

### 5-7. AppLog 활성화 범위 (§0-7)
**ERROR 이상만 캡처**. settings.LOGGING의 `applog_db` handler에 `level: "ERROR"`. 동기 INSERT (Phase 4에서 비동기 검토). 재귀 가드는 thread-local 플래그.

---

## 6. 발견 사항 / 부수 작업

### 6-1. dashboard 앱에 models/migrations 디렉토리 신규 생성

기존 dashboard 앱은 `menu.py` (하드코딩 메뉴 트리) + `views.py` + `urls.py`만 있었음. Phase 2-c에서 처음 모델이 들어가므로 `models/` + `migrations/` + `fixtures/` 디렉토리 신설. `dashboard/0001_initial.py`가 본 PR에서 생성됨.

기존 `dashboard/menu.py` 하드코딩 데이터는 fixture로 변환되었으나, **`menu.py` 파일 자체는 보존** — `dashboard/views.py`의 `get_menu_tree(role)`이 여전히 호출 중. Phase 4-a에서 DB 조회 전환 후 폐기 예정.

### 6-2. AppLog/IntegrationLog는 BaseModel 미상속

운영 로그(actor 없음 + 대량) 성격 + APPEND-ONLY 정책으로 SystemLog 패턴 차용. `created_at`만 직접 정의, `updated_at`/`updated_by` 없음 (수정 차단이라 무의미).

### 6-3. AlertPolicy.event_type vs USER_FACING_ALARM_TYPES

모델 레벨에서는 `AlarmType.choices` 전체(10종)를 허용. 화면에서는 `USER_FACING_ALARM_TYPES` 9종만 노출(SENSOR_FAULT 제외). 프론트에서 필터 처리.

### 6-4. drf_client `_record_integration_log` 재귀 가드

`post_to_drf` 자기 호출이 IntegrationLog 기록도 트리거 → 무한 루프 위험. `path != INTEGRATION_LOG_PATH` 체크로 회피.

### 6-5. ThresholdGroup/Threshold 시드 데이터 미포함

Phase 2-b는 모델만 신설. 시드 데이터(gas_legal/gas_facility_default 등)는 Phase 4-c에서 `gas_data.py risk` 계산 DB 조회 전환과 함께 작성. 그 전에 시드를 넣으면 운영 데이터와 코드 동작이 어긋날 수 있음.

---

## 7. Phase 2 외 / 후속 트랙

본 PR 범위 외 후속 항목:

### 7-1. Phase 3 (직렬, 운영 영향 큼)
- 3a. WorkerPosition.received_node FK + 펌웨어 동기
- 3b. SafetyCheckSection + SafetyCheckItem.section FK (마이그 2단계)
- 3c. SafetyChecklistRevision + SafetyCheckSession + SafetyStatus UNIQUE 변경 (마이그 4단계)
- 3d. Event 확장 (policy FK, description, status_note)
- 3e. Notification 확장 (policy FK, retry_count, last_attempted_at, event SET_NULL)

### 7-2. Phase 4 (서비스/뷰 전환)
- 4a. dashboard 메뉴 DB 조회 전환 (`get_menu_tree(role)` → Menu/RoleMenuVisibility 활용)
- 4b. `power_alarm.py` DB Threshold 조회
- 4c. `gas_data.py` risk 계산 DB 기반 + 캐시 도입
- 4d. `threshold_service.py` 재작성 (Threshold 시드 데이터 함께)
- 4e. AlertPolicy `policy_matcher` 서비스 + condition_summary 자동 갱신
- 4f. Notification `template_renderer` 서비스
- 4g. DataRetentionPolicy Celery 보관 배치

### 7-3. 운영 튜닝 (Phase 4 이후)
- AppLog 비동기 처리 (Celery 큐 또는 thread-pool) + 운영 부하 측정
- IntegrationLog batch flush 전환 (호출 ~2배 부담 측정 후)
- BaseModel 컨벤션 일괄 통일 PR (15개+ 직접 정의 모델)

---

## 8. 다음 Phase

[phase_2_plan.md](phase_2_plan.md) §7 미해결 + 부모 plan §3 의존 그래프에 따라 **Phase 3 관계 변경 PR**:
- WorkerPosition (펌웨어 의존)
- Safety 4단계 마이그레이션
- Event/Notification 확장

Phase 3는 운영 데이터에 영향이 크므로 (UNIQUE 변경, 마이그레이션 다단계) 단계별 분리 가능성 검토 필요. Phase 3 진입 전에 다시 plan 작성 + 사용자 확인 권장.
