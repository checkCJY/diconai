# B 운영 트랙 PR-C — DataRetentionPolicy 5종 + AlertPolicy 9종 기본 시드

> 작업일: 2026-05-09
> 브랜치: `feature/0508_refactory`
> 부모 plan: [`~/.claude/plans/b-cozy-panda.md`](../../../home/cjy/.claude/plans/b-cozy-panda.md) §3 PR-C
> 직전 PR: [post_phase4_b_track_pr_b_report.md](post_phase4_b_track_pr_b_report.md) (`7207a4c`)

---

## 1. 작업 목적

운영 진입 시점에 즉시 기본 알람/보관 동작이 가능하도록 두 정책 모델에 기본 시드 마이그 추가:
- **DataRetentionPolicy 5종** ([phase_4_pr3_report §7-4](phase_4_pr3_report.md))
- **AlertPolicy 9종** (USER_FACING_ALARM_TYPES, SENSOR_FAULT 제외)

`get_or_create` 패턴으로 idempotent 보장 — 운영자가 어드민에서 수정한 row는 마이그 재실행 시 보존됨.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `manage.py check` | ✅ 통과 |
| 마이그 일관성 | `makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그 적용 | `migrate` | ✅ alerts.0009 + operations.0003 |
| 시드 데이터 검증 | shell 호출 | ✅ AlertPolicy 9 + DataRetentionPolicy 5 |
| 마이그 reverse + re-apply | 양쪽 reverse → forward | ✅ idempotent (재실행 후 row 변경 없음) |
| pytest 회귀 (수정 후) | `.venv/bin/pytest` | ✅ **56 passed** |
| pre-commit | `pre-commit run --files <변경파일>` | ✅ Passed |

### 시드 데이터
```
AlertPolicy count: 9
  gas_threshold / power_overload / geofence_intrusion / ppe_violation
  safety_check_pending / vr_training_not_done / inspection_scheduled
  storage_overdue / batch_failed (모두 전사: target_facility=None)

DataRetentionPolicy count: 5
  gas_sensor / gas_raw / daily / 30 / 90
  gas_sensor / gas_anomaly / monthly_15 / 30 / 365
  power / power_raw / daily / 30 / 90
  power / power_agg / monthly_15 / 30 / 365
  position_node / position_hist / daily / 30 / 90
```

---

## 3. 변경 파일

### 3-1. 시드 마이그 (2개 신규)

| 파일 | 시드 |
|---|---|
| [drf-server/apps/operations/migrations/0003_seed_data_retention_default.py](../../drf-server/apps/operations/migrations/0003_seed_data_retention_default.py) | DataRetentionPolicy 5종 — phase_4_pr3 §7-4 권장 |
| [drf-server/apps/alerts/migrations/0009_seed_alert_policy_default.py](../../drf-server/apps/alerts/migrations/0009_seed_alert_policy_default.py) | AlertPolicy 9종 — USER_FACING_ALARM_TYPES (SENSOR_FAULT 제외) |

### 3-2. 회귀 테스트 갱신 (2개)

| 파일 | 변경 |
|---|---|
| [apps/operations/tests/test_data_retention.py](../../drf-server/apps/operations/tests/test_data_retention.py) | `RunDataRetentionTest.setUp()`에서 `DataRetentionPolicy.objects.all().delete()` 추가 — 시드된 5종 제거 후 테스트 진행 |
| [apps/alerts/tests/test_policy_matcher.py](../../drf-server/apps/alerts/tests/test_policy_matcher.py) | `setUpTestData()`에서 `AlertPolicy.objects.all().delete()` 추가 — 시드된 9종 제거 |

---

## 4. AlertPolicy 시드 9종 상세

| event_type | name | target_user_types | channels | message_template |
|---|---|---|---|---|
| gas_threshold | 가스 임계치 전사 알림 | super_admin, facility_admin, worker | popup | `{{ source_label }} 가스 위험 — {{ summary }}` |
| power_overload | 전력 과부하 전사 알림 | facility_admin, worker | popup | `{{ source_label }} 전력 과부하 — {{ summary }}` |
| geofence_intrusion | 위험구역 진입 전사 알림 | facility_admin, worker | popup | `{{ source_label }} 위험구역 진입 — {{ summary }}` |
| ppe_violation | PPE 미착용 전사 알림 | facility_admin | popup | `PPE 미착용 감지 — {{ source_label }}` |
| safety_check_pending | 안전 점검 미완료 전사 알림 | worker | popup | `안전 점검 미완료 — {{ summary }}` |
| vr_training_not_done | VR 교육 미이수 전사 알림 | worker | popup | `VR 교육 미이수 — {{ summary }}` |
| inspection_scheduled | 정기 점검 예정 전사 알림 | facility_admin | popup | `점검 예정 — {{ summary }}` |
| storage_overdue | 보관 주기 실패 전사 알림 | facility_admin | popup | `보관 주기 실패 — {{ summary }}` |
| batch_failed | 배치 실패 전사 알림 | super_admin | popup | `배치 실패 — {{ summary }}` |

policy_kind: immediate (모두). channels: popup (Phase 3-e 운영 채널). 운영 진입 시 어드민에서 push/sms/email 채널 인프라 도입 후 추가 설정.

---

## 5. 사용자 결정 사항 (B-track plan §2 결정 2)

| 항목 | 채택 | 본 PR 반영 |
|---|---|---|
| AlertPolicy seed 패턴 | (a) 9종 전사 정책 시드 + get_or_create idempotent | ✅ 시드 9종, target_facility=None |
| 어드민 변경 호환 | 시드는 초기값. 어드민 수정/추가/삭제 자유 | ✅ get_or_create로 운영자 수정 보존 |

---

## 6. 발견 사항 / 주의

### 6-1. 회귀 테스트 영향
시드 추가로 인해 기존 단위 테스트 6건이 UNIQUE 충돌 또는 가정 위배:
- `test_data_retention.py` 4건 — `(device_type, data_category)` UNIQUE 충돌
- `test_policy_matcher.py` 2건 — `match_policy()` None fallback 가정이 시드 정책 매칭으로 전환

**해결**: 두 테스트 클래스의 setUp/setUpTestData에서 해당 모델 `objects.all().delete()` 추가. 단위 테스트가 자체 fixture를 제어해야 한다는 일반 원칙.

### 6-2. e2e 회귀는 PR-H에서 검증
plan §2 결정 2의 "e2e 흐름 회귀"는 PR-H에서 본격적으로 검증. AlertPolicy seed가 들어왔으니 알람 task → match_policy → Notification 메시지 렌더 흐름이 비로소 e2e로 동작.

### 6-3. idempotent 검증 (재실행 안전)
```bash
migrate alerts 0009 → migrate alerts          # row 변경 0건
migrate operations 0003 → migrate operations  # row 변경 0건
```
get_or_create가 (event_type, target_facility, name) 또는 (device_type, data_category) 조합으로 기존 row 발견 시 skip — 운영자 수정 보존.

### 6-4. message_template 단순화 (Phase 4-f 일관)
모든 시드 정책의 message_template은 `{{ source_label }} ... {{ summary }}` 패턴. event 별 풍부한 분기는 운영자가 어드민에서 보강. Phase 4-f template_renderer가 graceful fallback (Event.summary 사용) 보장.

---

## 7. 다음 단계

PR-D (AppLog Celery + IntegrationLog batch flush) 진입. plan §3 PR-D.

---

## 8. 누적 결과

| PR | commit | 변경 |
|---|---|---|
| PR-A | `f4b50d0` | fixture 시드 마이그 historical apps 패턴 (4건) |
| PR-B | `7207a4c` | BaseModel 컨벤션 10개 모델 일괄 |
| **PR-C** | (본 commit) | DataRetentionPolicy 5종 + AlertPolicy 9종 시드 |
