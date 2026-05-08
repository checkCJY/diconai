# Phase 1~4 회귀 점검 — Step 2 fix 보고서

> 작업일: 2026-05-08
> 브랜치: `feature/0508_refactory`
> 부모 plan: [post_phase4_regression_plan.md](post_phase4_regression_plan.md) §4 Step 2
> 직전: [post_phase4_step1_report.md](post_phase4_step1_report.md) §9 (1A + 2A 결정)

---

## 1. 작업 목적

[Step 1 보고서](post_phase4_step1_report.md)에서 식별한 **유일한 회귀 위험 — POWER_THRESHOLDS 직접 사용 (DRF + FastAPI 양측)** 를 단일 진실 공급원 정책에 맞게 정리.

### 채택 조합 (Step 1 §9-3)
- **1A**: `Threshold` 모델에 `chart_max` 필드 추가 + fixture 갱신 + 마이그
- **2A**: FastAPI 측 docstring 강화 (코드 수정 없음)

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `python manage.py check` | ✅ 통과 (0 issues) |
| 마이그레이션 일관성 | `python manage.py makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그레이션 적용 | `python manage.py migrate facilities` | ✅ 0012 + 0013 두 단계 OK |
| **마이그 reverse + re-apply** | `migrate facilities 0011` → `migrate facilities` | ✅ 양방향 OK |
| 단위 테스트 (Phase 1~4 누적) | `python manage.py test (7 모듈)` | ✅ **29 tests OK** |
| ruff lint + format | `pre-commit run --files <변경파일>` | ✅ Passed |
| API 응답 형식 검증 | `PowerThresholdView` shell 호출 | ✅ `{caution: 2200.0, danger: 2860.0, maxY: 3500.0, unit: "W"}` (기존 구조 호환) |

### chart_max 백필 확인
```
power_w: warning_max=2200.0000 danger_max=2860.0000 chart_max=3500.0000 unit=W
```

---

## 3. 변경 파일 — 신규 (2개)

| 파일 | 역할 |
|---|---|
| [drf-server/apps/facilities/migrations/0012_threshold_chart_max.py](../../drf-server/apps/facilities/migrations/0012_threshold_chart_max.py) | `Threshold.chart_max` DecimalField(nullable) 컬럼 추가 (자동 생성) |
| [drf-server/apps/facilities/migrations/0013_backfill_chart_max.py](../../drf-server/apps/facilities/migrations/0013_backfill_chart_max.py) | RunPython — `power_default.power_w` row에 `chart_max=3500` 백필 (forward + reverse 명시) |

---

## 4. 변경 파일 — 기존 수정 (8개)

### 4-1. DRF 모델 / 서비스 / fixture (4개)

| 파일 | 변경 |
|---|---|
| [drf-server/apps/facilities/models/thresholds.py](../../drf-server/apps/facilities/models/thresholds.py) | `Threshold.chart_max` DecimalField 추가 (`max_digits=12, decimal_places=4, null=True, blank=True`). `verbose_name="차트 Y축 최대값"` |
| [drf-server/apps/facilities/services/threshold_service.py](../../drf-server/apps/facilities/services/threshold_service.py) | `get_threshold()` 반환 dict에 `chart_max` 키 추가. docstring 갱신 |
| [drf-server/apps/facilities/migrations/0011_seed_threshold_default.py](../../drf-server/apps/facilities/migrations/0011_seed_threshold_default.py) | **재작성**: `call_command("loaddata", ...)` → `apps.get_model()` 기반 explicit `update_or_create()`. 사유: fixture가 이후 마이그(0012)의 `chart_max` 필드를 미리 알 수 없어 새 환경 fresh migrate 시점에 `OperationalError: no such column: chart_max` 발생. historical apps 사용으로 해결. **운영 DB는 이미 0011 적용 완료라 영향 없음** (forward는 새 환경에서만 실행) |
| [drf-server/apps/facilities/fixtures/threshold_default.json](../../drf-server/apps/facilities/fixtures/threshold_default.json) | `power_w` row description만 갱신 (chart_max는 0013 백필에서 채움) |

### 4-2. DRF 호출자 (3개)

| 파일 | 변경 |
|---|---|
| [drf-server/apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py) | `fire_power_danger_task` + `fire_power_warning_task` 두 곳: `from apps.core.constants import POWER_THRESHOLDS` 제거 → `from apps.facilities.services.threshold_service import get_threshold`. `threshold = float(power_threshold.get("danger_max"))` / `warning_max` 패턴 (Decimal → float 변환 포함) |
| [drf-server/apps/monitoring/views/power_data.py](../../drf-server/apps/monitoring/views/power_data.py) | `PowerThresholdView.get()`: `Response(POWER_THRESHOLDS)` → `get_threshold("power_default", "power_w")` 조회 후 `{caution, danger, maxY, unit}` 4키 dict 합성. `_to_float()` helper로 Decimal/None → float/None 변환 (JSON 직렬화 호환). docstring에 단일 진실 공급원 정책 명시. OpenAPI schema에 maxY/unit 필드 추가 |
| [drf-server/apps/core/constants.py](../../drf-server/apps/core/constants.py) | `POWER_THRESHOLDS` dict 정의 (~127L) **삭제** — DB로 완전 이전 |

### 4-3. FastAPI docstring (3개) — 코드 수정 없음

| 파일 | 변경 |
|---|---|
| [fastapi-server/core/power_thresholds.py](../../fastapi-server/core/power_thresholds.py) | docstring 전면 갱신: "표시용 fallback" 명시 + DRF 단일 진실 공급원 정책 + 운영 진입 시 검토 사항 (DRF API fetch 캐시 옵션) 명시. `POWER_THRESHOLDS` dict 정의는 그대로 유지 |
| [fastapi-server/power/services/power_service.py](../../fastapi-server/power/services/power_service.py) | `build_equipment()` docstring 갱신: risk_level은 표시용, 실제 알람 판정 + DB 저장은 DRF의 `fire_power_*_task`가 담당 명시. 코드 동작은 그대로 |
| [fastapi-server/core/config.py](../../fastapi-server/core/config.py) | `POWER_THRESHOLD_CAUTION/DANGER` env 주석 갱신: "표시용 fallback. 실제 알람 판정은 DRF facilities.Threshold가 단일 진실 공급원" 명시 (이전: "DRF apps.core.constants.POWER_THRESHOLDS와 동일 값 유지" — DRF dict 제거됐으므로 갱신 필요) |

---

## 5. 사용자 결정 사항 ([Step 1 보고서 §9](post_phase4_step1_report.md#9-step-2-fix-세부-결정-2026-05-08-팀-공유용))

| 항목 | 채택 | 본 PR 반영 |
|---|---|---|
| §9-1 PowerThresholdView 응답 DB 기반화 | **A. Threshold.chart_max 필드 추가** | ✅ 마이그 2개 + 모델 + fixture + view |
| §9-2 FastAPI 측 처리 | **A. docstring 강화만** | ✅ 3개 파일 docstring 갱신, 코드 동작 그대로 |

---

## 6. 발견 사항 / 주의

### 6-1. 0011 마이그 재작성의 학습 가치

`call_command("loaddata", ...)`는 historical model state를 우회해 현재 모델 정의로 저장 시도. 따라서 **fixture 기반 seed 마이그는 이후 마이그가 추가되면 fresh migrate에서 깨질 수 있음**. 본 fix는 historical apps 패턴(`apps.get_model()` + `update_or_create()`)으로 재작성해 미래 변경에도 견딤.

향후 fixture seed 마이그 작성 시 **historical apps 패턴 권장** (Phase 1~4의 `core/0004_seed_risk_level_standard.py`, `dashboard/0002_seed_menu.py`도 동일 위험 보유 — 후속 트랙 검토).

### 6-2. PowerThresholdView 응답 호환성

기존 응답 `{caution: 2200, danger: 2860, maxY: 3500, unit: "W"}` (int + str). 신 응답은 `{caution: 2200.0, danger: 2860.0, maxY: 3500.0, unit: "W"}` (float + str). 프론트가 숫자 비교/표시만 한다면 호환. **OpenAPI schema도 갱신**되어 신규 클라이언트 생성 시 정확.

### 6-3. alerts/tasks.py threshold_value 형식

`AlarmRecord.threshold_value`는 FloatField. `get_threshold(...).get("danger_max")` 반환은 Decimal이라 `float(...)` 변환 필수. WS 페이로드 `{"threshold_value": threshold}`도 JSON 직렬화 위해 float여야 함.

### 6-4. FastAPI 측 자동 동기화 미적용 — 운영 진입 시점 재평가

FastAPI는 docstring만 갱신. `build_equipment()` risk_level은 표시용 fallback이라 어드민 Threshold 변경 시 자동 반영 안 됨 (env 재배포 필요). 학습 환경에서 OK이지만 **운영 진입 시 DRF API fetch 캐시 옵션 또는 펌웨어 합의 트랙과 묶을 수 있음** (Step 1 보고서 §9-2 채택 사유 일관).

### 6-5. POWER_THRESHOLDS 잔존 grep 결과 (모두 docstring/주석)

```
fastapi-server/core/power_thresholds.py: dict 정의 (표시용)
fastapi-server/power/services/power_service.py: 표시용 위험도 분기 + docstring
fastapi-server/core/config.py: env 주석
drf-server/apps/monitoring/services/power_alarm.py: docstring 이력 표기
drf-server/apps/facilities/services/threshold_service.py: docstring 이력 표기
drf-server/apps/facilities/migrations/0011_seed_threshold_default.py: docstring 이력 표기
drf-server/apps/facilities/migrations/0013_backfill_chart_max.py: docstring 이력 표기
```

DRF 측 코드 사용처 0건 (전부 historical reference / docstring). FastAPI 측은 1A+2A 결정대로 표시용 유지.

---

## 7. 다음 단계

[plan §4 Step 3](post_phase4_regression_plan.md): **핵심 흐름 5개 회귀 테스트 작성** (사용자 결정: 한 PR에 5개 묶기)

| 흐름 | 위치 (권장) |
|---|---|
| 가스 알람 | `apps/monitoring/tests/test_gas_alarm_flow.py` |
| 전력 알람 | `apps/monitoring/tests/test_power_alarm_flow.py` |
| 지오펜스 알람 | `apps/positioning/tests/test_geofence_alarm_flow.py` |
| 안전 체크리스트 (Session 도입 후) | `apps/safety/tests/test_check_item_flow.py` |
| 메뉴 트리 (DB + role 분기) | `apps/dashboard/tests/test_menu_tree.py` |

각 테스트는 Phase 1~4 변경 핵심을 회귀 커버:
- 가스: GasData.save() 단일 진실 공급원 (raw → DB Threshold 재계산)
- 전력: 본 fix에서 갱신한 fire_power_*_task 흐름 (DB Threshold 조회)
- 지오펜스: WorkerPosition.received_node FK
- 안전: SafetyCheckSession + mark_checked(session=, note=)
- 메뉴: dashboard/menu.py DB 조회 + role 분기 + 캐시
