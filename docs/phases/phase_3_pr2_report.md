# Phase 3 PR2 — Section + Event/Notification 확장 (3b + 3d + 3e)

> 작업일: 2026-05-08
> 브랜치: `feature/0508_refactory`
> 부모 plan: [.claude/plans/swirling-mixing-torvalds.md](../../.claude/plans/swirling-mixing-torvalds.md)
> 결정문: [phase_3_plan.md](phase_3_plan.md) §3b, §3d, §3e
> 직전 PR: [phase_3_pr1_report.md](phase_3_pr1_report.md)

---

## 1. 작업 목적

부모 plan §3 의존 그래프 [Phase 3 — PR2 (저위험 묶음)] 진입. 결정문 §3b + §3d + §3e의 모델 확장을 단일 PR로 묶음.

| Sub-step | 변경 |
|---|---|
| 3b | SafetyCheckSection 신설 + SafetyCheckItem.section FK (3단계 마이그: nullable → 백필 → NOT NULL) |
| 3d | Event 확장 (policy FK SET_NULL + description + status_note) |
| 3e | Notification 확장 (policy FK + retry_count + last_attempted_at + event CASCADE → SET_NULL) + clean() 갱신 |

§4-6 진행 중 명확화 항목 ⓒ (DELAYED 5분 timeout settings 상수화) + ⓓ (EventLog 확장 불필요 — 이미 note 필드 보유) 함께 반영.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `python manage.py check` | ✅ 통과 |
| 마이그레이션 일관성 | `python manage.py makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그레이션 적용 | `python manage.py migrate` | ✅ 5개 마이그 모두 적용 (alerts/0006, notifications/0002, safety/0003-0005) |
| **3단계 마이그 reverse 검증** | `migrate safety 0002` → `migrate safety` | ✅ Unapply (3 단계) + Re-apply (3 단계) 모두 OK |
| CI 정합성 테스트 회귀 | `python manage.py test apps.reference.tests... apps.core.tests... apps.alerts.tests.test_alarm_type_consistency` | ✅ 4 tests OK |
| ruff lint + format | `pre-commit run --files <변경파일>` | ✅ Passed |

### reverse 검증 흐름

```
[adapt-back]
  Unapplying safety.0005_safetycheckitem_section_not_null... OK   # NOT NULL → nullable
  Unapplying safety.0004_backfill_default_section... OK            # RunPython reverse: section=NULL 복원
  Unapplying safety.0003_safetychecksection_safetycheckitem_section_and_more... OK  # 모델/FK 제거

[re-apply]
  Applying safety.0003... OK                                       # 모델/FK 추가 (nullable)
  Applying safety.0004_backfill_default_section... OK              # facility별 "기본" Section + 백필
  Applying safety.0005_safetycheckitem_section_not_null... OK      # NOT NULL 전환
```

---

## 3. 변경 파일 — 신규 (5개)

### 3-1. 모델

| 파일 | 모델 | 역할 |
|---|---|---|
| [safety/models/safety_check_section.py](../../drf-server/apps/safety/models/safety_check_section.py) | `SafetyCheckSection` | 체크리스트 섹션 마스터 (공장별 + facility FK PROTECT). BaseModel 상속 + Soft Delete |

### 3-2. 마이그레이션

| 파일 | 역할 |
|---|---|
| `alerts/0006_event_description_event_policy_event_status_note.py` | Event에 description / status_note / policy FK 추가 (자동 생성) |
| `notifications/0002_notification_last_attempted_at_notification_policy_and_more.py` | Notification에 last_attempted_at / policy / retry_count + event CASCADE→SET_NULL (자동 생성) |
| `safety/0003_safetychecksection_safetycheckitem_section_and_more.py` | SafetyCheckSection 모델 + SafetyCheckItem.section FK nullable (자동 생성) |
| `safety/0004_backfill_default_section.py` | RunPython — facility별 "기본" Section 자동 생성 + 모든 NULL Item을 일괄 백필 (forward + reverse 코드 명시) |
| `safety/0005_safetycheckitem_section_not_null.py` | SafetyCheckItem.section nullable=False 전환 (백필 후 안전, 직접 작성) |

---

## 4. 변경 파일 — 기존 수정 (8개)

### 4-1. 모델

| 파일 | 변경 |
|---|---|
| [safety/models/safety.py](../../drf-server/apps/safety/models/safety.py) | `SafetyCheckItem.section` FK 추가 (PROTECT, related_name="items"). 마이그 1단계는 nullable, 5단계 적용 후 NOT NULL |
| [safety/models/__init__.py](../../drf-server/apps/safety/models/__init__.py) | `SafetyCheckSection` re-export |
| [alerts/models/event.py](../../drf-server/apps/alerts/models/event.py) | `description` (TextField, 상세 본문), `status_note` (TextField, 처리자 메모), `policy` FK (AlertPolicy, SET_NULL, related_name="events") 추가 |
| [notifications/models/notification.py](../../drf-server/apps/notifications/models/notification.py) | `event` FK CASCADE → SET_NULL + nullable, `policy` FK (AlertPolicy, SET_NULL), `retry_count` (PositiveInteger, default 0), `last_attempted_at` (DateTime nullable). `clean()`에 event/policy 중 하나 필수 검증 추가 |

### 4-2. settings / 어드민

| 파일 | 변경 |
|---|---|
| [config/settings.py](../../drf-server/config/settings.py) | `NOTIFICATION_DELAY_THRESHOLD_MINUTES = env.int(..., default=5)` 추가 — 동적 "지연" 판정 임계값 (§4-6 ⓒ) |
| [safety/admin.py](../../drf-server/apps/safety/admin.py) | `SafetyCheckSectionAdmin` 신규 등록. `SafetyCheckItemAdmin`에 section list_display + filter + select_related 추가 |
| [alerts/admin.py](../../drf-server/apps/alerts/admin.py) | EventAdmin에 policy list_display + filter, search_fields에 description/status_note 추가, list_select_related 확장 |
| [notifications/admin.py](../../drf-server/apps/notifications/admin.py) | NotificationAdmin에 retry_count list_display, readonly_fields에 last_attempted_at 추가 |

---

## 5. 사용자 결정 사항 (결정문 §3b + §3d + §3e)

### 5-1. 3b SafetyCheckSection — 6개 결정 모두 반영

| 항목 | 결정 | 본 PR |
|---|---|---|
| 3b-1 모델 필드 | name + description + order + facility FK + is_active + BaseModel | ✅ 표준 적용 |
| 3b-2 공장별 vs 전사 | 공장별 (facility FK 필수) | ✅ |
| 3b-3 자동 생성 정책 | facility별 "기본" Section 자동 + Item 백필 | ✅ 0004 RunPython |
| 3b-4 기존 Item 매핑 | 일괄 백필 | ✅ 0004 RunPython (모든 NULL row) |
| 3b-5 Section 삭제 정책 | PROTECT | ✅ on_delete=PROTECT |
| 3b-6 order 정합성 | (section.order, item.order) 두 레벨 | ✅ admin ordering, Index 정의 |

### 5-2. 3d Event 확장 — 5개 결정 모두 반영

| 항목 | 결정 | 본 PR |
|---|---|---|
| 3d-1 AlertPolicy FK | SET_NULL | ✅ on_delete=SET_NULL, null=True |
| 3d-2 description 의미 | summary(한 줄) + description(상세) 공존 | ✅ 두 필드 공존 + docstring 명시 |
| 3d-3 status_note 위치 | Event 본체 | ✅ Event.status_note |
| 3d-4 기존 row 처리 | nullable + default="" 자동 채움 | ✅ TextField(blank=True, default="") |
| 3d-5 자동 매칭 시점 | Phase 4-e policy_matcher가 채움 | ✅ Phase 3은 FK만, 매칭 로직 미포함 |

### 5-3. 3e Notification 확장 — 7개 결정 모두 반영

| 항목 | 결정 | 본 PR |
|---|---|---|
| 3e-1 event FK | CASCADE → SET_NULL + nullable | ✅ |
| 3e-2 clean() | event/policy 중 하나 필수 | ✅ ValidationError 추가 |
| 3e-3 retry_count | default 0 | ✅ PositiveInteger(default=0) |
| 3e-4 last_attempted_at | nullable + docstring | ✅ DateTimeField(null=True) + docstring |
| 3e-5 DELAYED | 동적 판정 (PENDING + 5분 timeout) | ✅ settings 상수 + docstring (화면 직렬화는 Phase 4-f template_renderer) |
| 3e-6 AlertPolicy FK | SET_NULL (3d-1과 동일) | ✅ |
| 3e-7 Soft Delete | Hard Delete | ✅ deactivated_at 미추가 |

### 5-4. §4-6 진행 중 명확화 5건 중 본 PR 처리

| # | 항목 | 본 PR 결정 |
|---|---|---|
| ⓒ | DELAYED 5분 임계값 | `settings.NOTIFICATION_DELAY_THRESHOLD_MINUTES = env.int(..., default=5)` 환경변수 override 가능 |
| ⓓ | status_note 이전 메모 보존 | EventLog에 이미 `note` 필드 존재 — 별도 모델 확장 불필요. 상태 전환 시 EventLog 생성 코드(Phase 4-e or 어드민 액션)에서 직전 status_note를 EventLog.note에 복사하면 됨 |

---

## 6. 발견 사항 / 주의

### 6-1. 5단계 마이그 분할의 학습 가치

3b의 nullable → 백필 → NOT NULL 3단계가 PR3 (3c의 5단계)을 위한 사전 학습 패턴. RunPython forward + reverse 코드 작성, AlterField로 NOT NULL 전환, reverse 검증 (`migrate safety 0002` → `migrate safety`)을 모두 검증 완료.

### 6-2. PR3 (3c)에 동일 패턴 적용 예정

PR3의 5단계는 본 3단계의 확장:
- (a) session FK nullable
- (b) RunPython 백필 (default Session)
- (c) UNIQUE(worker, check_item) drop
- (d) UNIQUE(session, check_item) add
- (e) session NOT NULL 전환

본 PR2의 0004 RunPython 백필 패턴 + 0005 AlterField 패턴이 그대로 차용 가능.

### 6-3. Notification.event SET_NULL 변경의 회귀

기존 v3 의도("Event 삭제 시 알림 자동 정리")는 사라짐. 단 운영 중 Event 삭제 케이스가 거의 없을 것 (Soft Delete 정책). Event 삭제 시 NULL 알림이 어느 출처인지는 `policy` FK 또는 `target_user` + `created_at`로 추적 가능.

### 6-4. AlertPolicy seed 미포함

본 PR은 AlertPolicy 인스턴스를 생성하지 않음 (모델만 Phase 2-f에 신설됨). Event.policy / Notification.policy는 Phase 4-e policy_matcher 도입 후 자동 채움. 그동안 모든 새 row의 policy=NULL이 정상 상태.

---

## 7. Phase 1, 2 plan 파일 위치 변경

기존 `~/.claude/plans/`에 있던 Phase 1/2 구현 plan을 `docs/phases/`로 복사 (보고서와 함께 보관):

| 이전 위치 | 현재 위치 |
|---|---|
| `~/.claude/plans/verdant-cascading-nebula.md` | [docs/phases/phase_1_plan.md](phase_1_plan.md) |
| `~/.claude/plans/lustrous-pivoting-meadow.md` | [docs/phases/phase_2_plan.md](phase_2_plan.md) |

phase_1_report.md / phase_2_report.md 안의 plan 링크도 신 위치로 갱신.

---

## 8. 다음 단계

PR3 — 3c. Session + Revision + UNIQUE 5단계 (가장 위험)
- SafetyChecklistRevision (JSON 스냅샷: Section 트리 + Item 메타)
- SafetyCheckSession (UNIQUE: worker, date, revision)
- SafetyStatus.session FK 5단계 마이그 (nullable → 백필 → old UNIQUE drop → new UNIQUE add → NOT NULL)
- mark_checked(session, note=None) 시그니처 변경 + 호출자 갱신
- §4-6 ⓔ: 5단계 reverse 단위 테스트
