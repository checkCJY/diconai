# Phase 1~4 회귀 점검 — Step 3 회귀 테스트 보고서

> 작업일: 2026-05-09
> 브랜치: `feature/0508_refactory`
> 부모 plan: [post_phase4_regression_plan.md](post_phase4_regression_plan.md) §4 Step 3
> 직전: [post_phase4_step2_report.md](post_phase4_step2_report.md)

---

## 1. 작업 목적

[Step 1 보고서](post_phase4_step1_report.md) §3 영향 영역과 [Step 2 fix](post_phase4_step2_report.md) 결과를 회귀 보호하기 위한 **핵심 흐름 5개 통합/단위 테스트** 추가.

### 사용자 결정
- **PR 단위**: 한 PR에 5개 묶기 (Step 1 §6-2 채택)
- **테스트 레벨**: 통합 4개 + 단위 1개 (메뉴 트리)
- **프레임워크**: pytest + pytest-django (drf-server 신규 도입, 기존 Django TestCase 29건도 pytest로 collect 가능)

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `python manage.py check` | ✅ 통과 |
| 마이그레이션 일관성 | `python manage.py makemigrations --dry-run --check` | ✅ "No changes detected" |
| pytest 전체 | `.venv/bin/pytest` | ✅ **56 passed** (기존 29 + 신규 27) |
| ruff lint + format | `pre-commit run --files <변경파일>` | ✅ Passed |

### 신규 회귀 테스트 27종

| 흐름 | 파일 | 테스트 수 | 레벨 |
|---|---|---|---|
| 가스 알람 | [apps/monitoring/tests/test_gas_alarm_flow.py](../../drf-server/apps/monitoring/tests/test_gas_alarm_flow.py) | 6 | 통합 |
| 전력 알람 | [apps/monitoring/tests/test_power_alarm_flow.py](../../drf-server/apps/monitoring/tests/test_power_alarm_flow.py) | 4 | 통합 |
| 지오펜스 알람 | [apps/positioning/tests/test_geofence_alarm_flow.py](../../drf-server/apps/positioning/tests/test_geofence_alarm_flow.py) | 5 | 통합 |
| 안전 체크리스트 | [apps/safety/tests/test_check_item_flow.py](../../drf-server/apps/safety/tests/test_check_item_flow.py) | 5 | 통합 |
| 메뉴 트리 | [apps/dashboard/tests/test_menu_tree.py](../../drf-server/apps/dashboard/tests/test_menu_tree.py) | 7 | 단위 |

---

## 3. 변경 파일 — 신규

### 3-1. pytest 인프라 (4개)

| 파일 | 역할 |
|---|---|
| [drf-server/pytest.ini](../../drf-server/pytest.ini) | DJANGO_SETTINGS_MODULE 지정 + 테스트 디스커버리 패턴 + `addopts = -ra --strict-markers` |
| [drf-server/conftest.py](../../drf-server/conftest.py) | 공통 fixture 5종 (`facility`, `gas_sensor`, `power_device`, `position_node`, `worker_user`). `db` fixture 의존 |
| [drf-server/requirements-dev.txt](../../drf-server/requirements-dev.txt) | `pytest==9.0.3`, `pytest-django==4.12.0` 신규 dev dep |
| [drf-server/apps/dashboard/tests/__init__.py](../../drf-server/apps/dashboard/tests/__init__.py) | namespace package → 일반 패키지 (다른 tests 디렉토리 일관) |

### 3-2. 회귀 테스트 5개 (위 §2 표)

#### 가스 알람 흐름 (test_gas_alarm_flow.py)
| 테스트 | 회귀 커버 |
|---|---|
| `test_gas_data_save_recalculates_risks_from_raw` | Phase 4-c 단일 진실 공급원 — raw 9종으로 *_risk 9종 + max_risk_level 자동 |
| `test_payload_risk_is_ignored_single_source_of_truth` | 페이로드 *_risk 잘못 주장해도 DB 기반 재계산이 우선 |
| `test_o2_below_danger_min_marks_danger` | O2 분기 (낮을수록 위험) — 15% < 16 (danger_min) → DANGER |
| `test_o2_between_warning_and_danger_marks_warning` | O2 17% — danger_min 이상 + warning_min 미만 → WARNING |
| `test_missing_gas_keeps_risk_none` | 미측정(None) 가스는 *_risk None 유지 |
| `test_all_missing_gas_max_risk_normal` | 전부 None → max_risk_level=normal default |

#### 전력 알람 흐름 (test_power_alarm_flow.py)
| 테스트 | 회귀 커버 |
|---|---|
| `test_get_threshold_returns_chart_max` | Step 2 fix — chart_max 백필 검증 |
| `test_evaluate_power_risk_normal_warning_danger` | Phase 4-b DB Threshold 기반 분기 7개 케이스 |
| `test_power_threshold_api_response_shape` | Step 2 fix — PowerThresholdView 응답 dict 구조(caution/danger/maxY/unit) 호환 |
| `test_admin_threshold_change_invalidates_cache` | signal invalidate — 어드민 변경 즉시 반영 |

#### 지오펜스 알람 흐름 (test_geofence_alarm_flow.py)
| 테스트 | 회귀 커버 |
|---|---|
| `test_position_with_valid_node_id_links_received_node` | Phase 3-a `received_node` FK 연결 |
| `test_position_with_unknown_node_id_falls_back_to_none` | 미존재 node_id silent fallback |
| `test_position_with_inactive_node_falls_back_to_none` | 비활성 PositionNode silent fallback |
| `test_position_with_none_node_id_keeps_received_node_null` | node_id=None 정상 처리 |
| `test_position_far_from_geofence_skips_save` | 지오펜스 근접 거리 밖 → 저장 생략 |

#### 안전 체크리스트 (test_check_item_flow.py)
| 테스트 | 회귀 커버 |
|---|---|
| `test_check_item_creates_session_and_status` | Phase 3 PR3 check_service.check_item() — Session/Status 자동 |
| `test_today_session_unique_per_worker_date_revision` | (worker, date, revision) UNIQUE — get_or_create 단일 보장 |
| `test_double_check_updates_existing_status` | (session, check_item) UNIQUE — 같은 날 재체크 시 갱신 |
| `test_mark_checked_requires_session_kwarg` | mark_checked(session=, note=) 시그니처 정상 호출 |
| `test_no_active_revision_raises` | 활성 Revision 부재 시 ValueError |

#### 메뉴 트리 (test_menu_tree.py) — 단위
| 테스트 | 회귀 커버 |
|---|---|
| `test_worker_menu_tree_excludes_admin_only` | Phase 4-a worker는 admin_only/admin_history 제외 |
| `test_super_admin_menu_tree_includes_admin_only` | super_admin은 모든 메뉴 |
| `test_menu_codes_are_snake_case` | 모든 코드 snake_case (이전 SNB-XX 폐기) |
| `test_menu_tree_response_shape` | 반환 형식 호환 (id/label/children) |
| `test_menu_tree_uses_cache_on_second_call` | 캐시 hit 동작 |
| `test_invalidate_menu_tree_cache_clears_all_roles` | invalidate 후 모든 role 캐시 무효 |
| `test_unknown_role_falls_back_to_worker` | 미존재 role graceful fallback |

---

## 4. 사용자 결정 사항 ([plan §4 Step 3](post_phase4_regression_plan.md))

| 항목 | 채택 | 본 PR |
|---|---|---|
| PR 단위 | 한 PR에 5개 묶기 | ✅ 본 PR `test : Phase 1~4 회귀 테스트 5종` |
| 테스트 레벨 | 통합 4개 + 단위 1개 | ✅ plan §9-4 권장 그대로 |
| 프레임워크 | pytest + pytest-django (Django TestCase에서 통일) | ✅ pytest로 기존 29건 + 신규 27건 모두 collect 가능 |

---

## 5. 발견 사항 / 주의

### 5-1. pytest 도입의 학습 가치

- pytest는 unittest.TestCase 기반 클래스도 자동 collect → 기존 29건 회귀 0건
- `pytest-django`의 `db` fixture로 transactional rollback 자동
- 새 회귀 테스트는 pytest 함수 + fixture 스타일 (parametrize 활용 가능)
- `pytest.mark.django_db` 데코레이터로 DB 접근 명시적 표기

### 5-2. conftest.py fixture scope

- 함수 단위 (default scope) 사용 — 테스트 간 격리. 회귀 테스트 목적상 격리가 우선
- session/module scope 도입은 향후 테스트 수가 100+ 이상 늘어날 때 검토

### 5-3. 캐시 의존성 회피

- `test_power_alarm_flow.py` / `test_menu_tree.py` 는 `clear_cache` autouse fixture로 각 테스트 전후 cache.clear() 보장
- Threshold/Menu signal invalidate가 자동 동작하므로 별도 invalidate 호출 불필요

### 5-4. Phase 4 PR2 (4ef) policy_matcher / template_renderer 회귀

본 PR은 plan §4의 5개 핵심 흐름에 집중 (사용자 결정). policy_matcher / template_renderer 자체 단위 테스트는 Phase 4 PR2에서 11건 작성됨 (`test_policy_matcher.py`, `test_template_renderer.py`) → 회귀 보호 충분.

알람 흐름 테스트(가스/전력/지오펜스)에서 policy_matcher/template_renderer 통합까지 검증하려면 `event_service.create_alarm_and_event` + `notification_service.notify_event_created` Celery 모킹 필요 → 본 PR 범위 외 (테스트 자체 비대화). 향후 통합 e2e 테스트 트랙으로 분리.

### 5-5. fastapi-server 측 회귀 테스트 미포함

본 회귀 테스트 5개는 모두 drf-server 측. fastapi-server는 별도 pytest 셋업이 필요하며 본 회귀 점검 PR 범위 외 (fastapi 측 단위 테스트는 별도 트랙).

---

## 6. 누적 결과 (Phase 1~4 회귀 점검 종료)

| 단계 | commit | 핵심 |
|---|---|---|
| Step 1 | `e81d800` (`docs : Step 1 회귀 점검 — 정적 영향 분석 보고서`) | grep 기반 영향 분석 8건 → 즉시 깨짐 0, 회귀 가능 1 (POWER_THRESHOLDS) |
| Step 2 | `eb04045` (`fix : POWER_THRESHOLDS DB 일원화`) | Threshold.chart_max + alerts/tasks.py + power_data.py + constants.py 정리 |
| Step 3 | (본 commit) `test : Phase 1~4 회귀 테스트 5종` | pytest 인프라 + 회귀 테스트 27건 |

**누적**: 56 단위/통합 테스트 통과, 모든 마이그 reverse 가능, 단일 진실 공급원 정책 일관 (DRF 측 100%).

---

## 7. 후속 트랙 (Step 3 외)

- **fastapi-server pytest 도입** — fastapi 측 단위/통합 테스트 (별도 트랙)
- **e2e 알람 흐름 통합 테스트** — Celery 모킹 + WebSocket 큐 검증 (별도 트랙)
- **POWER_THRESHOLDS FastAPI 자동 동기화** — 운영 진입 시 DRF API fetch 캐시 옵션 검토 ([Step 1 보고서 §9-2](post_phase4_step1_report.md#9-2-fastapi-corepower_thresholdspy-처리))
- **plan §7 운영 트랙 잔여**: BaseModel 컨벤션 일괄 통일, AppLog 비동기, AlertPolicy seed 등
- **다른 fixture-loaddata 마이그 점검**: `core/0004_seed_risk_level_standard`, `dashboard/0002_seed_menu` 등도 historical apps 패턴으로 갱신 검토 ([Step 2 보고서 §6-1](post_phase4_step2_report.md#6-1-0011-마이그-재작성의-학습-가치))
