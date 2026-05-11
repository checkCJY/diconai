# Phase 4 — 서비스/뷰/후처리 구현 plan

> 작성일: 2026-05-08
> 부모 plan: [.claude/plans/swirling-mixing-torvalds.md](../../.claude/plans/swirling-mixing-torvalds.md) §3 의존 그래프 [Phase 4]
> 직전 Phase: [phase_3_pr3_report.md](phase_3_pr3_report.md)

---

## Context

Phase 1~3은 모델·인프라 위주(이넘·앱·테이블·마이그레이션·시드)였고, Phase 4는 **서비스 로직 + 운영 흐름**을 그 위에 쌓는다.

부모 plan §3 의존 그래프의 [Phase 4 — 서비스 / 뷰 / 후처리] 7건을 3 PR로 분할.

| PR | Sub-step | 묶음 의도 |
|---|---|---|
| **PR1** | 4a + 4b + 4c + 4d | 임계치/메뉴 인프라 — DB 조회 전환 + Threshold 시드. 위험도 중(가스 알람 회귀 가능성). |
| **PR2** | 4e + 4f | AlertPolicy 매칭 + 템플릿 렌더 — 새 서비스 로직 추가, 기존 흐름 영향 적음. |
| **PR3** | 4g | Celery 보관 배치 — 단독 작업, 운영 시간 영향 큼 (배치 잘못되면 데이터 삭제). |

---

## 0. 사용자 결정 사항 (확정 ✅)

| 항목 | 결정 | 이유 |
|---|---|---|
| 진행 단위 | **2-3 PR 분할** | Phase 3 패턴 유지, 위험도 격리 |
| 캐시 백엔드 | **Redis (django-redis CACHES)** | 이미 인프라 있음, invalidate 가능, 프로세스 간 일관성 |
| Threshold seed | **본 PR(PR1) 포함** | 4b/4c/4d가 DB 조회로 전환되니 seed 없으면 알람 동작 차단 |
| 4f 템플릿 엔진 | **Django Template** | 알람 태스크 4개+ 분기 로직 필요(`fire_danger`/`fire_warning`/`fire_geofence`/`fire_threshold_recovered`), 향후 추가 가능성 큼 |

---

## 1. PR 분할 상세

### PR1 — 임계치/메뉴 인프라 (4a + 4b + 4c + 4d)

**작업:**
1. **4d. threshold_service.py 재작성** (선행) — Threshold DB 조회 함수 + Redis 캐시. 다른 모듈에서 이 함수만 사용하도록 단일 진입점.
2. **4d. Threshold seed** — 기존 [`core/constants.py POWER_THRESHOLDS`](drf-server/apps/core/constants.py#L101) + [`facilities/services/threshold_service.py LEGAL_THRESHOLDS`](drf-server/apps/facilities/services/threshold_service.py) 를 fixture로 이전. ThresholdGroup 2개 (`gas_legal`, `power_default`) + 가스 9종 + 전력 1종.
3. **4b. power_alarm.py 전환** — `from apps.core.constants import POWER_THRESHOLDS` 제거, threshold_service 호출로 교체.
4. **4c. gas_data risk 계산 전환** — `GasData.{gas}_risk` 계산 로직(serializer 또는 save 훅)을 threshold_service 호출 + Redis 캐시 기반으로. **정휘훈 권고 가장 중요한 작업**.
5. **4a. dashboard 메뉴 DB 조회** — `dashboard/menu.py`의 `get_menu_tree(role)` 함수를 Menu/RoleMenuVisibility DB 조회로 교체. Redis 캐시(role별 5분 TTL).
6. **RoleMenuVisibility 시드** — Phase 2-c에서 시드 안 됨. RoleProfile 모든 row × 모든 Menu = is_visible 매핑 자동 생성 (worker는 admin_only/admin_history 제외, 시설관리자/슈퍼관리자는 모두 visible).

**검증:**
- `manage.py migrate` (시드 마이그 1개 추가)
- `manage.py shell`: GasData 1건 INSERT → `{gas}_risk` 자동 계산 → 기존 결과와 동일 확인 (회귀)
- 알람 태스크 4종이 정상 작동 (`fire_danger_alarm_task` 등)
- `cache.delete()` 시그널 동작 확인

### PR2 — AlertPolicy 매칭 + 템플릿 (4e + 4f)

**작업:**
1. **4e. policy_matcher 서비스** (`apps/alerts/services/policy_matcher.py`):
   - `match_policy(event_type, facility_id, sensor_id=None, device_id=None, geofence_id=None) -> AlertPolicy | None`
   - AlertPolicy 조회: target_facility 일치 + event_type 일치 + target_sensor_ids/device_ids/geofence_ids JSON 매칭 (또는 비어있으면 전체)
   - `compute_condition_summary(policy: AlertPolicy) -> str` — 화면 캐시 컬럼 채우기 (Phase 2-f)
2. **4e. AlertPolicy.save 시 condition_summary 갱신** — service 레이어에서 `save_policy(policy)` 호출 시 자동. signal 안 씀(컨벤션).
3. **4f. template_renderer 서비스** (`apps/notifications/services/template_renderer.py`):
   - `render_alert_message(template: str, context: dict) -> str` — Django Template 활용
   - AlertPolicy에 `message_template` TextField 추가 (default="")
   - Notification 발송 시점에 policy.message_template + context로 렌더 → Notification.message 채우기
4. **알람 태스크 통합** — Phase 3-d Event.policy / 3-e Notification.policy FK가 채워지도록 `fire_*_alarm_task`에서 policy_matcher + template_renderer 호출.

**검증:**
- 단위 테스트: `match_policy` 4개 케이스 (일치/불일치/전사/특정)
- 단위 테스트: `render_alert_message` Django Template 분기 (위험도별)
- 알람 흐름 통합 회귀 (가스 임계치 → AlertPolicy 매칭 → 템플릿 → Notification.message)

### PR3 — DataRetentionPolicy Celery 배치 (4g)

**작업:**
1. **Celery 태스크** (`apps/operations/tasks/data_retention_task.py`):
   - `run_data_retention()` — DataRetentionPolicy.objects.filter(is_active=True) 순회
   - device_type + data_category에 따라 GasData/PowerData/WorkerPosition 삭제 분기
   - raw_retention_days 초과 row → 삭제, history_retention_days 초과 row → 추가 정리
   - delete_cycle 따라 실행 여부 판정 (DAILY/MONTHLY_1/MONTHLY_15/MONTHLY_LAST/QUARTERLY)
2. **Celery beat 스케줄** (`config/celery.py` 또는 settings.CELERY_BEAT_SCHEDULE):
   - 매일 새벽 3시 `run_data_retention` 실행
3. **dry-run 모드** — `run_data_retention(dry_run=True)` 옵션. 실제 삭제 안 하고 대상 row 수만 로그.

**검증:**
- 단위 테스트: dry_run=True에서 삭제 안 됨 + 대상 row 수 로깅
- 단위 테스트: delete_cycle 판정 (오늘 날짜에 따라 실행/스킵)
- 수동 실행: `celery -A config call apps.operations.tasks.data_retention_task.run_data_retention --args='[true]'`

---

## 2. PR 의존 그래프

```
PR1 (4abcd) — Threshold/Menu 인프라
  ↓ (Threshold/Menu seed가 들어와야 PR2 동작)
PR2 (4ef) — AlertPolicy 매칭 + 템플릿
  ↓ (PR2의 알람 태스크 통합 검증 완료 후)
PR3 (4g) — Celery 보관 배치 (독립)
```

PR3는 PR1/2와 독립적이므로 병렬 가능하지만, Phase 일관성을 위해 직렬 진행.

---

## 3. Critical Files

### 변경 대상

**PR1:**
- [drf-server/apps/facilities/services/threshold_service.py](drf-server/apps/facilities/services/threshold_service.py) — 재작성
- [drf-server/apps/monitoring/services/power_alarm.py](drf-server/apps/monitoring/services/power_alarm.py) — DB 조회 전환
- [drf-server/apps/monitoring/serializers/gas_data.py](drf-server/apps/monitoring/serializers/gas_data.py) — risk 계산 전환 (또는 모델 save 훅)
- [drf-server/apps/dashboard/menu.py](drf-server/apps/dashboard/menu.py) — DB 조회로 교체 (또는 dashboard/views.py 직접)
- 신규: `drf-server/apps/facilities/fixtures/threshold_default.json`
- 신규: `drf-server/apps/dashboard/migrations/0003_seed_role_menu_visibility.py` (또는 fixture)

**PR2:**
- 신규: `drf-server/apps/alerts/services/policy_matcher.py`
- 신규: `drf-server/apps/notifications/services/template_renderer.py`
- [drf-server/apps/alerts/models/alert_policy.py](drf-server/apps/alerts/models/alert_policy.py) — `message_template` 필드 추가
- [drf-server/apps/alerts/tasks.py](drf-server/apps/alerts/tasks.py) — fire_*_alarm_task에 policy_matcher + template_renderer 호출

**PR3:**
- 신규: `drf-server/apps/operations/tasks/__init__.py`, `data_retention_task.py`
- [drf-server/config/settings.py](drf-server/config/settings.py) — `CELERY_BEAT_SCHEDULE` 추가

---

## 4. 검증 흐름 (각 PR 공통)

```bash
cd drf-server
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --dry-run --check
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test apps.<관련앱>.tests
pre-commit run --files <변경파일>
```

PR1 추가:
- 알람 회귀 테스트 — gas_alarm.py / power_alarm.py 호출 시 기존 동작 일치
- Threshold 시드 확인 (`ThresholdGroup.objects.count() >= 2`)

PR2 추가:
- `match_policy` / `render_alert_message` 단위 테스트
- 통합: 알람 발생 → Event.policy 채워짐 → Notification.message 렌더됨

PR3 추가:
- dry_run 모드 단위 테스트
- delete_cycle 판정 로직 단위 테스트

---

## 5. 위험 / 주의

### 5-1. 4c gas_data risk 계산 전환 (PR1 핵심)

기존 `{gas}_risk`는 어디서 계산되는지 정확한 grep 필요. serializer/save 훅/model property 중 하나. 캐시 도입 시:
- `cache.get(f"threshold:gas:{gas_type}")` → 미존재 시 DB 조회 → set
- Threshold 변경 시 `post_save` 시그널로 `cache.delete_pattern("threshold:gas:*")`

운영 회귀 위험: 기존 위험도 판정 결과와 동일해야 함. 단위 테스트로 강제.

### 5-2. RoleMenuVisibility 자동 시드 정책

worker는 `admin_only`/`admin_history` 메뉴 제외, facility_admin/super_admin은 모두 visible. 이 정책을 fixture 또는 RunPython으로 자동 생성.

### 5-3. 4g Celery 배치 — DataRetentionPolicy 시드 부재

DataRetentionPolicy seed는 Phase 1에서 미작성 (모델만 신설). 운영자가 어드민에서 직접 생성하거나 본 PR에서 default 정책 1~3개 자동 시드 가능. 결정문 §3a~§3e와 별도 항목 → PR3 작성 시 결정.

### 5-4. AlertPolicy.message_template 마이그

PR2에서 message_template 필드 추가 → 마이그레이션 1개. 기존 row default="" 자동 채움. 위험 0.

---

## 6. Phase 4 종료 후

- 모델 변경 거의 없음 (4e의 message_template 1개만)
- 서비스 로직 + 알람 흐름 + 메뉴 DB 조회 + 보관 배치 모두 완성
- 운영 배포 가능 상태 (학습 환경 기준)

다음 단계 (Phase 4 외 트랙):
- AppLog 비동기 처리 (Celery 큐 또는 thread-pool)
- IntegrationLog batch flush 전환
- BaseModel 컨벤션 일괄 통일 PR (15개+ 모델)
- 펌웨어 측 합의 후 3a NULL row 정리
