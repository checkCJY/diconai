# Phase 4 PR3 — DataRetentionPolicy Celery 보관 배치 (4g)

> 작업일: 2026-05-08
> 브랜치: `feature/0508_refactory`
> Phase plan: [phase_4_plan.md](phase_4_plan.md)
> 직전 PR: [phase_4_pr2_report.md](phase_4_pr2_report.md)

---

## 1. 작업 목적

Phase 4 plan §1 PR3 — DataRetentionPolicy 자동 보관 배치 구현. Phase 1에서 신설한 정책 모델이 비로소 운영 흐름에 연결됨.

| 작업 | 효과 |
|---|---|
| `run_data_retention` Celery 태스크 | DataRetentionPolicy 순회 → device_type/data_category 분기 → 보관 기간 초과 row 삭제 |
| `is_cycle_due` 헬퍼 | DAILY/MONTHLY_1/MONTHLY_15/MONTHLY_LAST/QUARTERLY 5종 cycle 판정 |
| `dry_run` 모드 | 실제 삭제 없이 대상 row 수만 반환 — 운영 적용 전 검증 |
| Celery beat 스케줄 | 매일 새벽 3시 자동 실행 (`crontab(hour=3, minute=0)`) |

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `python manage.py check` | ✅ 통과 |
| 마이그레이션 일관성 | `python manage.py makemigrations --dry-run --check` | ✅ "No changes detected" |
| 단위 테스트 (PR3 신규 10) | `python manage.py test apps.operations.tests.test_data_retention` | ✅ 10 tests OK |
| 전체 회귀 (PR3 + 기존) | 7개 모듈 전체 | ✅ **29 tests OK** |
| ruff lint + format | `pre-commit run --files <변경파일>` | ✅ Passed |

### PR3 단위 테스트 10종

[apps/operations/tests/test_data_retention.py](../../drf-server/apps/operations/tests/test_data_retention.py):

| 클래스 / 테스트 | 검증 |
|---|---|
| `IsCycleDueTest.test_daily_always_true` | DAILY는 모든 날짜에 True |
| `IsCycleDueTest.test_monthly_1` | 1일만 True, 그 외 False |
| `IsCycleDueTest.test_monthly_15` | 15일만 True |
| `IsCycleDueTest.test_monthly_last` | 평년/윤년 2월 말일, 5월 31일 등 정확 |
| `IsCycleDueTest.test_quarterly` | 3/31, 6/30, 9/30, 12/31만 True |
| `IsCycleDueTest.test_unknown_cycle_returns_false` | 미지원 cycle은 False |
| `RunDataRetentionTest.test_no_active_policy_returns_empty` | 정책 0건 → 빈 dict |
| `RunDataRetentionTest.test_dry_run_does_not_delete` | dry_run=True에서 카운트만, 실제 삭제 X |
| `RunDataRetentionTest.test_actual_run_deletes_old_rows` | 100일 전 row 삭제, 10일 전 row 보존 |
| `RunDataRetentionTest.test_skip_when_cycle_not_due` | quarterly 정책이 평일에는 스킵 (mock으로 today=5/8 설정) |

---

## 3. 변경 파일 — 신규 (3개)

| 파일 | 역할 |
|---|---|
| [operations/tasks/__init__.py](../../drf-server/apps/operations/tasks/__init__.py) | tasks 패키지 초기화 + `run_data_retention`/`is_cycle_due` re-export |
| [operations/tasks/data_retention_task.py](../../drf-server/apps/operations/tasks/data_retention_task.py) | Celery `@shared_task` 진입점 + `is_cycle_due()` cycle 판정 헬퍼 + `_delete_for_policy()` 카테고리별 삭제 분기 |
| [operations/tests/test_data_retention.py](../../drf-server/apps/operations/tests/test_data_retention.py) | cycle 판정 6 + 실행 4 = 10 tests |

---

## 4. 변경 파일 — 기존 수정 (1개)

[config/settings.py](../../drf-server/config/settings.py):

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "data_retention_daily": {
        "task": "apps.operations.tasks.data_retention_task.run_data_retention",
        "schedule": crontab(hour=3, minute=0),
        "args": (False,),  # dry_run=False (실제 삭제)
    },
}
```

Celery beat 실행: `celery -A config beat -l info` (worker와 별도 프로세스).

---

## 5. 데이터 카테고리별 삭제 분기

| data_category | 모델 | 필터 | 기준 |
|---|---|---|---|
| `gas_raw` | GasData | `max_risk_level="normal"` + `measured_at < now - raw_retention_days` | 정상 데이터는 raw 보관 |
| `gas_anomaly` | GasData | `max_risk_level != "normal"` + `measured_at < now - history_retention_days` | 이상 이력은 더 길게 보관 |
| `power_raw` | PowerData | `measured_at < now - raw_retention_days` | |
| `power_agg` | PowerData | `measured_at < now - history_retention_days` | |
| `position_hist` | WorkerPosition | `measured_at < now - raw_retention_days` | |

미지원 category는 logger.warning 후 0 반환.

---

## 6. 사용자 결정 사항

본 PR은 결정문에서 별도 항목 없음. Phase 4 plan §5 위험 항목 그대로:
- DataRetentionPolicy seed는 운영자가 어드민에서 직접 생성 (자동 시드 안 함)
- 기본 실행 시간은 새벽 3시
- dry_run 모드 제공

---

## 7. 발견 사항 / 주의

### 7-1. dry_run 모드의 가치

본 PR을 운영 적용할 때 첫 실행은 반드시 `run_data_retention.delay(dry_run=True)`로 호출 후 `summary` 로그 확인 권장. Celery beat은 default dry_run=False라 즉시 실제 삭제 실행 — 정책이 잘못 설정됐을 때 데이터 손실 위험.

운영 패턴:
1. 어드민에서 DataRetentionPolicy 생성/수정
2. 다음 새벽 3시 전에 `celery -A config call apps.operations.tasks.data_retention_task.run_data_retention --args='[true]'` 수동 실행 (dry_run=True)
3. 로그에서 대상 row 수 확인
4. 문제없으면 그대로 두고 새벽 3시에 실제 삭제 자동 진행

### 7-2. test_skip_when_cycle_not_due의 timezone mock

해당 테스트는 `apps.operations.tasks.data_retention_task.timezone.now`를 patch해서 today=2026-05-08을 강제. 그러나 실제로 본 코드는 `timezone.now().date()`만 사용하므로 mock된 `now()` → date 변환이 정상 작동. 향후 timezone 처리가 더 복잡해지면 freezegun 도입 검토.

### 7-3. Celery Worker 동시성

`run_data_retention`은 `@shared_task`이지만 동시 실행 시 같은 row를 두 번 삭제 시도할 수 있음. Celery beat은 기본 1 worker에만 분배하므로 학습 환경에서는 문제 없음. 운영 시 lock 또는 `acks_late=True` 검토.

### 7-4. DataRetentionPolicy seed 미포함

본 PR은 기본 정책을 자동 생성하지 않음. 운영자가 어드민에서 다음 5종을 직접 생성해야 동작:
- (gas_sensor, gas_raw, daily, raw=30, history=90)
- (gas_sensor, gas_anomaly, monthly_15, raw=30, history=365)
- (power, power_raw, daily, raw=30, history=90)
- (power, power_agg, monthly_15, raw=30, history=365)
- (position_node, position_hist, daily, raw=30, history=90)

향후 fixture로 시드할지는 별도 결정.

---

## 8. Phase 4 종료

PR1 (4abcd) + PR2 (4ef) + PR3 (4g)로 **Phase 4 의존 그래프 7건 모두 완료**.

| PR | Sub-step | 핵심 |
|---|---|---|
| PR1 | 4a, 4b, 4c, 4d | 임계치/메뉴 인프라 — Threshold seed + Redis 캐시 + GasData 단일 진실 공급원 + 메뉴 DB 조회 |
| PR2 | 4e, 4f | AlertPolicy 매칭 + Notification 템플릿 — Event.policy/Notification.policy FK 자동 채움 |
| PR3 | 4g | DataRetentionPolicy Celery 배치 — 보관 기간 초과 row 자동 정리 |

Phase 1~4 누적: **15 commits, 모든 모델·서비스·운영 흐름 완성**. 운영 배포 가능 상태 (학습 환경 기준).

---

## 9. Phase 4 외 / 후속 트랙

부모 plan §2-10 + Phase 4 plan §6의 미해결 항목:
- AppLog 비동기 처리 (Celery 큐 또는 thread-pool) + 운영 부하 측정
- IntegrationLog batch flush 전환 (호출 ~2배 측정 후)
- BaseModel 컨벤션 일괄 통일 PR (15개+ 직접 정의 모델)
- 펌웨어 측 합의 후 3a NULL row 정리
- DataRetentionPolicy 기본 seed (5종)
- Threshold facility별 정책 (gas_facility_default 그룹)
- AlertPolicy seed (운영자가 어드민에서 생성)
- 화면 구현 (어드민 패널, 사이드 메뉴, 알람 화면 등)
