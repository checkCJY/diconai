# Phase 3 PR3 — Session + Revision + UNIQUE 5단계 (3c)

> 작업일: 2026-05-08
> 브랜치: `feature/0508_refactory`
> 부모 plan: [.claude/plans/swirling-mixing-torvalds.md](../../.claude/plans/swirling-mixing-torvalds.md)
> 결정문: [phase_3_plan.md](phase_3_plan.md) §3c
> 직전 PR: [phase_3_pr2_report.md](phase_3_pr2_report.md)

---

## 1. 작업 목적

부모 plan §3 의존 그래프 [Phase 3 — PR3 (별도, 가장 위험)] 진입. 결정문 §3c의 **Session + Revision + UNIQUE 5단계 마이그**를 단일 PR에 묶음.

| 변경 | 효과 |
|---|---|
| `SafetyChecklistRevision` 신설 | 발행 시점 동결 스냅샷 (감사 요구). facility별 1개 active. |
| `SafetyCheckSession` 신설 | (worker, date, revision) UNIQUE — 1일 1세션 + 개정별 분리. |
| `SafetyStatus.session` FK + UNIQUE 변경 | 기존 (worker, check_item) 1인 1항목 영구 고정 → (session, check_item) 1세션 1항목으로 **매일 체크 지원**. |
| `mark_checked()` 시그니처 변경 | session 필수 키워드 인자 (silent error 방지). |
| `check_service.py` 재작성 | `get_or_create_today_session` 헬퍼 + `check_item()` 단순화. |

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `python manage.py check` | ✅ 통과 |
| 마이그레이션 일관성 | `python manage.py makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그레이션 적용 | `python manage.py migrate` | ✅ 5개 마이그 모두 OK (safety/0006~0010) |
| **5단계 reverse + re-apply** | `migrate safety 0005` → `migrate safety` | ✅ 5단계 unapply (역순) + 5단계 re-apply 모두 OK |
| 단위 테스트 | `python manage.py test apps.safety.tests apps.reference.tests... apps.alerts.tests...` | ✅ **8 tests OK** (CI 정합성 4 + Session/Revision 4) |
| ruff lint + format | `pre-commit run --files <변경파일>` | ✅ Passed |

### 5단계 reverse 흐름 (결정문 §4-6 ⓔ)

```
[reverse]
  Unapplying safety.0010_safetystatus_session_not_null...           # NOT NULL → nullable
  Unapplying safety.0009_add_new_status_unique...                   # UNIQUE(session, check_item) drop
  Unapplying safety.0008_drop_old_status_unique...                  # UNIQUE(worker, check_item) 복원
  Unapplying safety.0007_backfill_default_session...                # RunPython reverse: session=NULL
  Unapplying safety.0006_safetychecklistrevision_safetychecksession_and_more...  # 모델 제거

[re-apply]
  Applying safety.0006...                                            # Revision/Session 모델 + nullable session
  Applying safety.0007_backfill_default_session...                  # facility별 default Revision/Session 백필
  Applying safety.0008_drop_old_status_unique...                    # 구 UNIQUE 제거
  Applying safety.0009_add_new_status_unique...                     # 신 UNIQUE(session, check_item)
  Applying safety.0010_safetystatus_session_not_null...             # NOT NULL 전환
```

### 단위 테스트 4종 (Session/Revision)

[apps/safety/tests/test_session_migration.py](../../drf-server/apps/safety/tests/test_session_migration.py):

| 테스트 | 검증 |
|---|---|
| `test_session_unique_worker_date_revision` | (worker, date, revision) UNIQUE 강제 — 같은 조합 중복 INSERT는 IntegrityError |
| `test_revision_facility_active_unique` | facility별 active Revision 1개 — 부분 UniqueConstraint(is_active=True) |
| `test_status_unique_session_item` | (session, check_item) UNIQUE — 신 제약 동작 확인 |
| `test_mark_checked_signature` | `mark_checked(session=..., note=...)` 정상 호출 + state 갱신 |

---

## 3. 변경 파일 — 신규 (8개)

### 3-1. 모델 (2개)

| 파일 | 모델 | 역할 |
|---|---|---|
| [safety/models/safety_checklist_revision.py](../../drf-server/apps/safety/models/safety_checklist_revision.py) | `SafetyChecklistRevision` | 발행 시점 동결 스냅샷 (revision_data JSON: Section 트리 + Item 메타). facility별 1개 active 부분 UniqueConstraint |
| [safety/models/safety_check_session.py](../../drf-server/apps/safety/models/safety_check_session.py) | `SafetyCheckSession` | 1일 1세션 단위 (worker, date, revision UNIQUE). is_completed 추적 |

### 3-2. 마이그레이션 (5개)

| 파일 | 단계 | 역할 |
|---|---|---|
| `safety/0006_safetychecklistrevision_safetychecksession_and_more.py` | (a) | Revision/Session 모델 + SafetyStatus.session nullable FK 추가 |
| `safety/0007_backfill_default_session.py` | (b) | RunPython — facility별 default Revision(version=1, is_active=True, revision_data={"sections":[]}) + (worker, date, revision) Session get_or_create + SafetyStatus.session 매핑 |
| `safety/0008_drop_old_status_unique.py` | (c) | RemoveConstraint(uq_safety_worker_item) — 구 UNIQUE 제거 |
| `safety/0009_add_new_status_unique.py` | (d) | AddConstraint(UniqueConstraint(session, check_item, name=uq_safety_session_item)) |
| `safety/0010_safetystatus_session_not_null.py` | (e) | AlterField session nullable=False (PROTECT 유지) |

### 3-3. 단위 테스트

| 파일 | 검증 |
|---|---|
| [safety/tests/test_session_migration.py](../../drf-server/apps/safety/tests/test_session_migration.py) | Session/Revision UNIQUE 4건 (위 §2 표 참조) |

---

## 4. 변경 파일 — 기존 수정 (4개)

| 파일 | 변경 |
|---|---|
| [safety/models/safety.py](../../drf-server/apps/safety/models/safety.py) | `SafetyStatus.session` FK 추가 (PROTECT, related_name="statuses"). 모델 정의 최종 상태(NOT NULL + UNIQUE(session, check_item))로 갱신. `mark_checked(session, note=None)` 시그니처 변경 (session 필수). docstring 갱신 (3차 한계 표기 → Phase 3-c 변경 표기) |
| [safety/models/__init__.py](../../drf-server/apps/safety/models/__init__.py) | `SafetyChecklistRevision`, `SafetyCheckSession` re-export |
| [safety/services/check_service.py](../../drf-server/apps/safety/services/check_service.py) | `get_or_create_today_session(worker_id, facility_id)` 신규 헬퍼. `check_item()` 단순화 — 내부에서 today session 조회 후 `mark_checked(session=...)`. `can_complete_session()` 재작성 — session 기반으로 단순화 (3차 "오늘 체크 여부 = checked_at.date() 비교" 우회 제거) |
| [safety/admin.py](../../drf-server/apps/safety/admin.py) | `SafetyChecklistRevisionAdmin`, `SafetyCheckSessionAdmin` 신규 등록. `SafetyStatusAdmin`에 session list_display + select_related 추가 |

---

## 5. 사용자 결정 사항 (결정문 §3c) — 9개 결정 모두 반영

| 항목 | 결정 | 본 PR |
|---|---|---|
| 3c-1 Session 식별 키 | `(worker, date, revision)` 복합 UNIQUE | ✅ UniqueConstraint with 3 fields |
| 3c-2 1일 1세션 정책 | 차단 + 기존 세션 이어가기 | ✅ `get_or_create_today_session` (get_or_create) |
| 3c-3 Revision JSON 스냅샷 | Section 트리 + Item 메타 | ✅ revision_data JSONField, docstring에 형식 명시 |
| 3c-4 발행 트리거 | 관리자 수동 | ✅ 모델만 신설, ActionType `CHECKLIST_REVISION_PUBLISHED`는 Phase 1에서 추가됨 |
| 3c-5 ActionType | Phase 1 결정됨 | ✅ 본 PR 변경 없음 |
| 3c-6 기존 SafetyStatus 매핑 | default Session 1개 자동 + 일괄 매핑 | ✅ 0007 RunPython (worker별 default Session) |
| 3c-7 5단계 마이그 분할 | 5단계 (a~e) | ✅ 0006~0010 |
| 3c-8 mark_checked() 시그니처 | session 필수 키워드 인자 | ✅ `def mark_checked(self, session, note=None)` |
| 3c-9 무중단 vs 점검창 | N/A (학습 환경) | ✅ |

§4-6 진행 중 명확화 ⓔ — 5단계 reverse 단위 테스트:
- 정식 reverse 명령(`migrate safety 0005` + `migrate safety`)으로 양방향 검증 완료
- 모델 레벨 테스트 4종으로 UNIQUE 제약 보강 (보고서 §2)

---

## 6. 발견 사항 / 주의

### 6-1. RunPython 백필의 facility 추론

[0007_backfill_default_session.py](../../drf-server/apps/safety/migrations/0007_backfill_default_session.py)는 `SafetyStatus.check_item.facility_id`로 facility 추론. `check_item=NULL`인 row(탈퇴/삭제된 항목 이력)는 facility 추론 불가 → `session=NULL`로 남음.

학습 환경에서는 사실상 0건이지만, 운영 시점에는 (e) NOT NULL 전환 전 별도 정리 마이그 필요할 수 있음. 본 PR은 학습 환경 전제로 그대로 진행 (결정문 §3c 결정 일관).

### 6-2. revision_data 빈 트리

마이그 자동 생성한 default Revision은 `revision_data={"sections": []}` 빈 트리. 운영자가 정식 발행 화면(Phase 4 외 트랙)에서 첫 v1을 채우면 됨. 백필용 placeholder 의도.

### 6-3. check_service.check_item() 동작 변경

이전: `worker_id` + `item_id` → `(worker, check_item)` get_or_create + `mark_checked(note)`
이후: `worker_id` + `item_id` → today session 조회 → `(session, check_item)` get_or_create + `mark_checked(session=, note=)`

**호출 시그니처는 동일** (`check_item(worker_id, item_id, note="")`). 내부 로직만 변경 → 호출자 영향 없음.

### 6-4. PR2의 3단계 마이그 패턴 → PR3의 5단계 확장

PR2가 닦아놓은 RunPython forward/reverse + AlterField NOT NULL 패턴을 그대로 차용. 추가로 RemoveConstraint/AddConstraint 2개 단계가 더 들어감 (UNIQUE 변경 분리).

### 6-5. SafetyStatus 모델 정의 vs 마이그 history

SafetyStatus 모델 정의는 **최종 상태**로 갱신(session NOT NULL, UNIQUE(session, check_item)). 마이그 0006~0010이 단계적으로 그 상태로 도달. `makemigrations --dry-run --check` "No changes detected"로 일관성 확인.

만약 향후 SafetyStatus를 추가 변경한다면 0011_부터 누적되며, 모델 정의는 항상 최신 상태를 유지.

---

## 7. Phase 3 종료

PR1 (3a) + PR2 (3b+3d+3e) + PR3 (3c)로 **Phase 3 의존 그래프 5건 모두 완료**. 다음은 Phase 4 — 서비스/뷰/후처리:

- 4a. dashboard 메뉴 DB 조회 전환 (Menu/RoleMenuVisibility 활용)
- 4b. power_alarm.py DB Threshold 조회
- 4c. gas_data risk 계산 DB 기반 + 캐시 도입
- 4d. threshold_service.py 재작성
- 4e. AlertPolicy `policy_matcher` 서비스 + condition_summary 자동 갱신
- 4f. Notification `template_renderer` 서비스
- 4g. DataRetentionPolicy Celery 보관 배치

운영 튜닝 (Phase 4 이후):
- AppLog 비동기 처리 + 운영 부하 측정
- IntegrationLog batch flush 전환
- BaseModel 컨벤션 일괄 통일 PR (15개+ 모델)
- 펌웨어 측 합의 후 3a NULL row 정리 (학습 환경에서는 발생 안 함)
