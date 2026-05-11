# Phase 4 PR1 — 임계치/메뉴 인프라 (4a + 4b + 4c + 4d)

> 작업일: 2026-05-08
> 브랜치: `feature/0508_refactory`
> Phase plan: [phase_4_plan.md](phase_4_plan.md)
> 직전 PR: [phase_3_pr3_report.md](phase_3_pr3_report.md)

---

## 1. 작업 목적

Phase 4 plan §3 PR1 — 4가지 인프라 작업을 단일 PR로 묶음:

| Sub-step | 작업 |
|---|---|
| 4d | `threshold_service.py` 재작성 + Redis 캐시 + invalidate signal + Threshold seed fixture |
| 4b | `power_alarm.py`에서 `POWER_THRESHOLDS` 상수 제거 → `evaluate_power_risk()` 호출 |
| 4c | `GasData.save()`에서 raw 측정값 기반 risk 9종 재계산 (단일 진실 공급원) |
| 4a | `dashboard.menu.get_menu_tree()` DB 조회 전환 + Redis 캐시 + invalidate signal |

부수: RoleProfile 4종 자동 시드 + RoleMenuVisibility 자동 매핑.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `python manage.py check` | ✅ 통과 |
| 마이그레이션 일관성 | `python manage.py makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그레이션 적용 | `python manage.py migrate` | ✅ 3개 RunPython 시드 모두 OK |
| Threshold 캐시 + risk 평가 회귀 | `evaluate_gas_risk` / `evaluate_power_risk` 9개 케이스 | ✅ 모두 정확 |
| 메뉴 트리 DB 조회 | `get_menu_tree('worker')` | ✅ 2개 그룹(safety + monitoring) + 자식 메뉴 정상 (admin_only 제외) |
| CI 정합성 4종 + Session 4종 | `python manage.py test ...` | ✅ 8 tests OK |
| ruff lint + format | `pre-commit run --files <변경파일>` | ✅ Passed |

### Risk 평가 검증 (4c 핵심)

```
co=10  → normal   (warning_max=25)
co=30  → warning  (warning_max=25 ~ danger_max=200)
co=200 → danger   (>= danger_max)
o2=20  → normal   (warning_min=18 ~ warning_max=23.5)
o2=17  → warning  (< warning_min=18, >= danger_min=16)
o2=15  → danger   (< danger_min=16)
watt=2000 → normal
watt=2500 → warning  (> warning_max=2200)
watt=3000 → danger   (> danger_max=2860)
```

기존 fastapi/core/gas_thresholds.py + core/constants.POWER_THRESHOLDS와 동일 동작 확인.

---

## 3. 변경 파일 — 신규 (5개)

### 3-1. 서비스 / 시그널 (3개)

| 파일 | 역할 |
|---|---|
| [facilities/signals.py](../../drf-server/apps/facilities/signals.py) | Threshold post_save/post_delete → 캐시 invalidate (group_code, item) |
| [dashboard/signals.py](../../drf-server/apps/dashboard/signals.py) | Menu/RoleMenuVisibility post_save/post_delete → 모든 role 메뉴 트리 캐시 무효화 |
| [facilities/fixtures/threshold_default.json](../../drf-server/apps/facilities/fixtures/threshold_default.json) | ThresholdGroup 2 (gas_legal + power_default) + Threshold 10 (가스 9종 + 전력 1종) |

### 3-2. 마이그레이션 (3개)

| 파일 | 역할 |
|---|---|
| `accounts/0010_seed_role_profile.py` | RoleProfile 4종 시드 (super_admin/facility_admin/worker/viewer) |
| `dashboard/0003_seed_role_menu_visibility.py` | RoleProfile × Menu visibility 자동 매핑. worker/viewer는 admin_only/admin_history 제외 |
| `facilities/0011_seed_threshold_default.py` | RunPython loaddata `threshold_default` fixture |

---

## 4. 변경 파일 — 기존 수정 (5개)

### 4-1. threshold_service.py 전면 재작성

[facilities/services/threshold_service.py](../../drf-server/apps/facilities/services/threshold_service.py):

| 이전 | 이후 |
|---|---|
| `LEGAL_THRESHOLDS` dict 상수 (가스 10종) | `get_threshold(group_code, item) -> dict | None` — DB 조회 + Redis 캐시 |
| `FACILITY_THRESHOLDS` 미완성 dict | 제거 (DB 모델로 대체) |
| `get_legal_threshold()` 함수 | `evaluate_gas_risk(gas, value) -> RiskLevel` (O2 분기 포함) |
| — | `evaluate_power_risk(watt) -> RiskLevel` (power_alarm 위임) |
| — | `invalidate_threshold_cache(group_code, item=None)` (signal에서 호출) |

### 4-2. apps.py — signal 연결

| 파일 | 변경 |
|---|---|
| [facilities/apps.py](../../drf-server/apps/facilities/apps.py) | `ready()`에서 signals 모듈 import |
| [dashboard/apps.py](../../drf-server/apps/dashboard/apps.py) | 동일 |

### 4-3. 알람/모델 코드 전환

| 파일 | 변경 |
|---|---|
| [monitoring/services/power_alarm.py](../../drf-server/apps/monitoring/services/power_alarm.py) | `from apps.core.constants import POWER_THRESHOLDS` 제거 → `from apps.facilities.services.threshold_service import evaluate_power_risk` 추가. `_evaluate(watt)`이 evaluate_power_risk 위임 |
| [monitoring/models/gas_data.py](../../drf-server/apps/monitoring/models/gas_data.py) | `recalculate_risks_from_thresholds()` 메서드 신규 — raw 측정값(co/h2s/...)으로부터 *_risk 9종을 DB Threshold 기반 재계산. `save()`에서 max_risk_level 계산 전 호출 → **단일 진실 공급원**: fastapi가 보낸 risk 페이로드는 무시, DRF Threshold가 마스터 |
| [dashboard/menu.py](../../drf-server/apps/dashboard/menu.py) | 전면 재작성. `_MENU_WORKER`/`_MENU_ADMIN_EXTRA` 하드코딩 제거. `get_menu_tree(role)`은 RoleProfile + RoleMenuVisibility + Menu DB 조회. role별 5분 TTL Redis 캐시. `_build_menu_tree`로 트리 구성. `invalidate_menu_tree_cache()` 함수 — signal에서 호출 |

---

## 5. 사용자 결정 사항 (Phase 4 plan §0 반영)

| 항목 | 결정 | 본 PR |
|---|---|---|
| 진행 단위 | 2-3 PR 분할 | ✅ PR1 = 4abcd |
| 캐시 백엔드 | Redis (django-redis CACHES) | ✅ 모든 캐시 `from django.core.cache import cache` |
| Threshold seed | 본 PR 포함 | ✅ fixture + RunPython 마이그 (12 row) |

---

## 6. 발견 사항 / 주의

### 6-1. 4c 단일 진실 공급원 정책

기존: fastapi `core/gas_thresholds.py`가 risk 계산 → 페이로드에 *_risk 포함 → DRF가 그대로 저장
이후: DRF `GasData.save()`가 raw 측정값(co/h2s/...) 기반으로 **재계산**. 페이로드 risk 무시.

**효과:**
- fastapi와 DRF의 임계치 분기 위험 제거
- 운영자가 어드민에서 Threshold 수정 → 다음 GasData 저장부터 즉시 반영
- 캐시(Redis 1시간 TTL + signal invalidate)로 부하 최소

**부수 효과:**
- fastapi-server `core/gas_thresholds.py`는 더미 생성용으로만 의미 (DRF의 risk 결과와 일관성 유지 필요)
- 향후 fastapi 측 위험도 계산 코드도 정리 가능 (Phase 4 외 트랙)

### 6-2. RoleProfile.code 형식

`UserType.values` 그대로 사용 (`super_admin`, `facility_admin`, `worker`, `viewer`). RoleProfile 4종 자동 시드되어 dashboard 메뉴 트리 DB 조회 가능.

### 6-3. 메뉴 트리 캐시 TTL

5분 TTL + signal invalidate. 운영자가 어드민에서 메뉴 수정 → 즉시 모든 role 캐시 무효화 → 다음 요청에서 새 트리 반영.

### 6-4. 기존 menu.py 보존

PR1은 `get_menu_tree(role)` 함수 시그니처 유지. 호출자(dashboard/views.py)는 변경 없음. 내부 구현만 DB 조회로 교체.

### 6-5. POWER_THRESHOLDS 상수는 그대로 유지

[core/constants.py](../../drf-server/apps/core/constants.py#L101-L106)의 `POWER_THRESHOLDS` 상수는 본 PR에서 제거하지 않음. 다른 모듈(특히 fastapi 더미)에서 참조하지 않는지 grep 후 별도 PR에서 cleanup 권장.

```bash
grep -rn "POWER_THRESHOLDS" /home/cjy/diconai --include="*.py"
```

---

## 7. 다음 단계 (PR2 예정)

[Phase 4 plan §1 PR2 (4ef)](phase_4_plan.md#pr2--alertpolicy-매칭--템플릿-4e--4f):
- AlertPolicy `policy_matcher` 서비스 + `condition_summary` 자동 갱신
- Notification `template_renderer` 서비스 (Django Template 엔진)
- 알람 태스크 4종 (`fire_*_alarm_task`)에 policy_matcher + template_renderer 통합

PR3 (4g): DataRetentionPolicy Celery 보관 배치 — 단독 작업.
