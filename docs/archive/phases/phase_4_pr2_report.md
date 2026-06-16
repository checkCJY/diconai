# Phase 4 PR2 — AlertPolicy 매칭 + Notification 템플릿 (4e + 4f)

> 작업일: 2026-05-08
> 브랜치: `feature/0508_refactory`
> Phase plan: [phase_4_plan.md](phase_4_plan.md)
> 직전 PR: [phase_4_pr1_report.md](phase_4_pr1_report.md)

---

## 1. 작업 목적

Phase 4 plan §1 PR2 — AlertPolicy 자동 매칭 + Notification 메시지 동적 렌더.

| Sub-step | 작업 |
|---|---|
| 4e | `policy_matcher` 서비스 — Event 트리거 정보로 AlertPolicy 자동 매칭, condition_summary 자동 갱신 |
| 4f | `template_renderer` 서비스 — Django Template으로 Notification.message 동적 렌더 |
| 통합 | `event_service.create_alarm_and_event`에서 policy_matcher 호출 → Event.policy 채움 |
| 통합 | `notification_service.notify_event_created`에서 template_renderer 호출 → Notification.message 채움 |

Phase 3-d/3-e에서 추가했던 Event.policy / Notification.policy FK가 비로소 자동 채워지는 흐름 완성.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `python manage.py check` | ✅ 통과 |
| 마이그레이션 일관성 | `python manage.py makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그레이션 적용 | `python manage.py migrate` | ✅ `alerts.0007_alertpolicy_message_template` |
| 단위 테스트 | `python manage.py test ...` | ✅ **19 tests OK** (PR2 신규 11 + 기존 8) |
| ruff lint + format | `pre-commit run --files <변경파일>` | ✅ Passed |

### PR2 신규 단위 테스트 11종

| 파일 | 테스트 | 검증 |
|---|---|---|
| [alerts/tests/test_policy_matcher.py](../../../drf-server/apps/alerts/tests/test_policy_matcher.py) | `test_match_specific_facility` | target_facility 일치 매칭 |
| | `test_match_global_policy_when_facility_specific_absent` | 전사(NULL) 정책 fallback |
| | `test_match_specific_takes_priority_over_global` | 특정 facility > 전사 우선순위 |
| | `test_no_match_returns_none` | 일치 없음 → None |
| | `test_save_policy_updates_condition_summary` | save_policy() condition_summary 자동 갱신 |
| | `test_compute_condition_summary_global` | 전사 정책 요약에 "전사" 포함 |
| [notifications/tests/test_template_renderer.py](../../../drf-server/apps/notifications/tests/test_template_renderer.py) | `test_simple_substitution` | 단순 변수 치환 |
| | `test_if_branch_danger` | `{% if level == 'danger' %}` 분기 |
| | `test_if_branch_warning` | `{% if level == 'danger' %}{% else %}` 분기 |
| | `test_empty_template_returns_fallback` | 빈 템플릿 → fallback |
| | `test_syntax_error_returns_fallback` | TemplateSyntaxError → fallback |

---

## 3. 변경 파일 — 신규 (3개)

| 파일 | 역할 |
|---|---|
| [alerts/services/policy_matcher.py](../../../drf-server/apps/alerts/services/policy_matcher.py) | `match_policy(event_type, facility_id, sensor_id, device_id, geofence_id) -> AlertPolicy | None` — 구체성 점수 기반 매칭 (target_facility 2점 + 자산 매칭 1점). `compute_condition_summary(policy)` 화면 캐시 문자열. `save_policy(policy)` — condition_summary 자동 갱신 진입점 |
| [notifications/services/template_renderer.py](../../../drf-server/apps/notifications/services/template_renderer.py) | `render_alert_message(template, context, fallback="")` — Django Template 렌더 + graceful fallback (TemplateSyntaxError/Exception 모두 logger.warning 후 fallback 반환) |
| [alerts/migrations/0007_alertpolicy_message_template.py](../../../drf-server/apps/alerts/migrations/0007_alertpolicy_message_template.py) | AlertPolicy.message_template TextField 추가 |

신규 테스트 2개도 함께:
- `alerts/tests/test_policy_matcher.py`
- `notifications/tests/test_template_renderer.py`

---

## 4. 변경 파일 — 기존 수정 (3개)

### 4-1. AlertPolicy 모델

[alerts/models/alert_policy.py](../../../drf-server/apps/alerts/models/alert_policy.py):
```python
message_template = TextField(
    blank=True, default="", verbose_name="알림 메시지 템플릿",
    help_text="Django Template 문법. 빈 값이면 Event.summary 사용"
)
```
docstring에 예시 포함: `"{{ source_label }}에서 {% if level == 'danger' %}🚨 긴급{% else %}⚠️ 주의{% endif %}"`

### 4-2. event_service 통합

[alerts/services/event_service.py](../../../drf-server/apps/alerts/services/event_service.py) 의 `create_alarm_and_event` — 새 Event 생성 직전 `match_policy()` 호출. 결과를 `Event.objects.create(policy=policy, ...)`로 전달.

```python
from apps.alerts.services.policy_matcher import match_policy
policy = match_policy(
    event_type=alarm_type, facility_id=facility_id,
    sensor_id=sensor_id, device_id=power_device_id, geofence_id=geofence_id,
)
event = Event.objects.create(..., policy=policy, ...)
```

병합 케이스(active_event 존재)는 policy 갱신 안 함 — 첫 Event 생성 시점에 매칭 1회.

### 4-3. notification_service 통합

[notifications/services/notification_service.py](../../../drf-server/apps/notifications/services/notification_service.py) 의 `notify_event_created`:
- Event.policy → Notification.policy FK 자동 전달
- AlertPolicy.message_template + context로 `render_alert_message()` 호출
- 빈 템플릿/렌더 실패 시 Event.summary fallback (graceful)

context 표준 키: `source_label`, `risk_level`, `level`, `summary`, `facility_name`, `event_type`. 향후 알람 태스크에서 추가 키(`gas_name`, `value`, `unit` 등) 전달 가능 — 본 PR은 기본 키 6종 보장.

---

## 5. 사용자 결정 사항 (Phase 4 plan §0 반영)

| 항목 | 결정 | 본 PR |
|---|---|---|
| 템플릿 엔진 | Django Template (사용자 결정 — 알람 분기 필요) | ✅ `from django.template import Template, Context` |
| AlertPolicy.target_user_types | JSON (Phase 1 결정) | ✅ 본 PR 추가 변경 없음 |
| condition_summary 갱신 | service 레이어(`save_policy()`) | ✅ signal/save 오버라이드 안 함 (CLAUDE.md 컨벤션 일관) |

---

## 6. 발견 사항 / 주의

### 6-1. 알람 태스크 4종은 자동 통합

`fire_danger_alarm_task` / `fire_warning_alarm_task` / `fire_geofence_alarm_task` / `fire_power_*` 등 알람 태스크는 모두 `event_service.create_alarm_and_event()`를 호출. 본 PR이 그 진입점에 policy_matcher를 통합했으므로 **태스크 코드 수정 0** — 자동으로 Event.policy / Notification.policy 채워짐.

### 6-2. 빈 AlertPolicy 환경 안전

운영 초기 AlertPolicy가 0개일 때:
- `match_policy()` → None 반환
- `Event.policy = None` 저장 (Phase 3-d FK SET_NULL/null=True 보장)
- `Notification.policy = None`, `notification.message = event.summary` (fallback)

운영 흐름 차단 없이 graceful degradation.

### 6-3. condition_summary 갱신 흐름

`AlertPolicy.objects.create()` 직접 호출은 condition_summary 비어있는 채로 저장됨. **service 진입점으로 `save_policy(policy)` 사용 권장** — view에서 `policy = AlertPolicy(...)` + `save_policy(policy)`.

향후 Phase 4-e에 어드민 액션도 `save_policy()`로 통합 권장 (본 PR 미포함, 어드민 폼은 직접 save 사용 중).

### 6-4. 매칭 점수 시스템

- target_facility=NULL (전사): facility_score=0
- target_facility=일치: facility_score=2
- 자산 제약(sensor/device/geofence_ids) 있고 일치: asset_score=1
- 자산 제약 없음: asset_score=0
- 자산 제약 있고 불일치: 매칭 제외 (점수 None)

가장 구체적인 정책 1건 우선. 동점 시 query 순서(가장 먼저 매칭된 것).

### 6-5. Django Template 보안

알람 메시지는 운영자가 어드민에서 입력. `{% load %}` 등 위험 태그를 막을지는 본 PR에서 결정 안 함. 학습 환경에서 OK이지만 운영 시 검토 필요 (custom Engine + restricted builtins).

---

## 7. 다음 단계 (PR3 예정)

[Phase 4 plan §1 PR3 (4g)](phase_4_plan.md):
- `apps.operations.tasks.data_retention_task.run_data_retention()` Celery 태스크
- DataRetentionPolicy 순회 → device_type/data_category 분기 → GasData/PowerData/WorkerPosition 삭제
- Celery beat 스케줄 (매일 새벽 3시)
- dry_run 모드 (`run_data_retention(dry_run=True)`)
- 단위 테스트: dry_run + delete_cycle 판정
