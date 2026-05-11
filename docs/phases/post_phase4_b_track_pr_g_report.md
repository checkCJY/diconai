# B 운영 트랙 PR-G — Threshold facility별 정책 (gas_facility_default)

> 작업일: 2026-05-09
> 브랜치: `feature/0508_refactory`
> 부모 plan: [`~/.claude/plans/b-cozy-panda.md`](../../../home/cjy/.claude/plans/b-cozy-panda.md) §3 PR-G
> 직전 PR: [post_phase4_b_track_pr_f_report.md](post_phase4_b_track_pr_f_report.md) (`f647d93`)

---

## 1. 작업 목적

phase_2_report §6-5 명시 — facility별 보수적 정책(gas_facility_default) 도입. 이전엔 모든 공장이 gas_legal(법정) 임계치만 사용 → A공장(밀폐 화학)/B공장(개방 조립) 동일 기준. 운영 진입 시 어드민에서 facility별 강화된 정책을 입력할 수 있는 인프라 마련.

[사용자 결정 4 — 작업량 재산정 결과 "중"](`/home/cjy/.claude/plans/b-cozy-panda.md#§2-사용자-결정-사항-확정`): 시계열 데이터 비대와 무관 (Threshold는 정책 마스터 — row 수십 개). PR-G 본 plan 포함.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `manage.py check` | ✅ 통과 |
| 마이그 일관성 | `makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그 적용 | `migrate` | ✅ facilities.0015 + 0016 OK |
| 마이그 reverse + re-apply | `migrate facilities 0014` → `migrate facilities` | ✅ OK |
| pytest 회귀 + 신규 | `.venv/bin/pytest` | ✅ **58 passed** (기존 56 + facility 우선순위 신규 2건) |
| pre-commit | `pre-commit run --files <변경파일>` | ✅ Passed |

### 누적
- drf-server: **58 tests** (기존 56 + 신규 2)
- fastapi-server: **22 tests** (PR-F 그대로)
- 총합: **80 tests**

---

## 3. 변경 파일

### 3-1. 모델 + 마이그 (3개)

| 파일 | 변경 |
|---|---|
| [apps/facilities/models/thresholds.py](../../drf-server/apps/facilities/models/thresholds.py) | `Threshold.facility = FK(Facility, null=True, blank=True, on_delete=CASCADE)` 추가. UNIQUE 제약 (`group, measurement_item`) → (`group, measurement_item, facility`). docstring에 facility 우선순위 정책 명시 |
| [apps/facilities/migrations/0015_threshold_facility_fk.py](../../drf-server/apps/facilities/migrations/0015_threshold_facility_fk.py) | facility FK 추가 + RemoveConstraint + AddConstraint (자동 생성) |
| [apps/facilities/migrations/0016_seed_facility_default_group.py](../../drf-server/apps/facilities/migrations/0016_seed_facility_default_group.py) | gas_facility_default ThresholdGroup 시드 (RunPython, get_or_create idempotent). 실제 facility별 Threshold row는 운영자 어드민 입력 |

### 3-2. 서비스 시그니처 변경

| 파일 | 변경 |
|---|---|
| [apps/facilities/services/threshold_service.py](../../drf-server/apps/facilities/services/threshold_service.py) | `get_threshold(group, item, facility_id=None)` — facility specific row 우선 조회 후 facility=NULL fallback. `evaluate_gas_risk(gas, value, facility_id=None)` — gas_facility_default 그룹 우선 매칭 후 gas_legal fallback. 캐시 키 `threshold:{group}:{item}:{facility_id}` (facility None은 "all"). `invalidate_threshold_cache` 시그니처 확장 |
| [apps/facilities/signals.py](../../drf-server/apps/facilities/signals.py) | post_save/post_delete signal에서 `instance.facility_id`도 함께 invalidate 호출 |
| [apps/monitoring/models/gas_data.py](../../drf-server/apps/monitoring/models/gas_data.py) | `recalculate_risks_from_thresholds()`에서 `self.gas_sensor.facility_id`를 `evaluate_gas_risk(gas, value, facility_id=facility_id)` 전달. docstring PR-G 변경 명시 |

### 3-3. 회귀 테스트 신규 (2건)

| 파일 | 테스트 |
|---|---|
| [apps/monitoring/tests/test_power_alarm_flow.py](../../drf-server/apps/monitoring/tests/test_power_alarm_flow.py) | `test_facility_specific_threshold_overrides_legal` — gas_facility_default 그룹 row 추가 후 facility specific 우선 매칭 확인. `test_facility_without_specific_falls_back_to_legal` — facility specific row 부재 시 gas_legal fallback 확인 |

---

## 4. 사용자 결정 사항 (B-track plan §2 결정 4)

| 항목 | 채택 | 본 PR 반영 |
|---|---|---|
| facility별 Threshold | (a) PR-G로 본 plan 포함 | ✅ Threshold.facility FK + 우선순위 로직 + gas_facility_default 그룹 시드 |
| 작업량 재평가 | "대" → "중" (시계열 비대와 무관, Threshold는 정책 마스터) | ✅ 마이그 2개 + 시그니처 변경 + 호출자 1곳 + 테스트 2건 |

---

## 5. 발견 사항 / 주의

### 5-1. 가스 vs 전력의 facility 정책 차이

| 그룹 | facility 차원 | 시드 정책 |
|---|---|---|
| gas_legal | 전사 (facility=NULL) | 9 row (PR-A 시드) |
| gas_facility_default | facility별 specific | 그룹만 시드 — row는 운영자 입력 |
| power_default | 전사 (facility=NULL) | 1 row (PR-A 시드) |

전력은 power_default 1개 그룹 (facility 무관, 전사) — `evaluate_power_risk(watt)` 시그니처에 facility_id 매개변수 없음. PR-G 영향 0.

### 5-2. CASCADE 정책

`Threshold.facility = FK(on_delete=CASCADE)`. facility 삭제 시 해당 facility의 Threshold도 함께 삭제. Facility는 Soft Delete 정책상 실제 delete가 거의 없음 (is_active=False). CASCADE는 안전.

### 5-3. fallback 흐름

```
evaluate_gas_risk(gas="co", value=15, facility_id=42)
  → 1. get_threshold("gas_facility_default", "co", facility_id=42)
       → facility=42 row 존재 시 사용 (warning_max=10)
  → 2. None이면 fallback to gas_legal: get_threshold("gas_legal", "co")
       → facility=NULL row 사용 (warning_max=25)
  → 3. 둘 다 None이면 RiskLevel.NORMAL (graceful)
```

### 5-4. Step 3 회귀 테스트 영향 0

기존 `test_gas_alarm_flow.py` 6건은 `evaluate_gas_risk(gas, value)` 호출 — facility_id 미지정 (기본값 None) → gas_legal fallback 그대로 사용. 모두 통과 확인.

### 5-5. 어드민 입력 가이드

운영자가 어드민에서 facility별 Threshold 입력 시:
1. `ThresholdGroup`에서 `gas_facility_default` 그룹 선택
2. `Threshold.facility` 드롭다운에서 대상 공장 선택
3. `measurement_item`(co/h2s/...) + warning_max/danger_max/chart_max 입력
4. 저장 → signal이 캐시 invalidate → 다음 GasData.save 즉시 반영

---

## 6. 다음 단계

PR-H (e2e 알람 흐름 통합 테스트) 진입. 본 plan 마지막 PR.

---

## 7. 누적 결과

| PR | commit | 변경 |
|---|---|---|
| PR-A | `f4b50d0` | fixture 시드 마이그 historical apps 패턴 |
| PR-B | `7207a4c` | BaseModel 컨벤션 10개 모델 |
| PR-C | `81e70de` | DataRetentionPolicy + AlertPolicy 시드 |
| PR-D | `cdbeddd` | AppLog/IntegrationLog Celery 비동기 |
| PR-E | `af80d69` | GasTypeChoices.LEL dead code 제거 |
| PR-F | `f647d93` | fastapi-server pytest 인프라 + 22 스모크 |
| **PR-G** | (본 commit) | Threshold.facility FK + 우선순위 로직 + gas_facility_default |

**누적 pytest**: drf-server 58 + fastapi-server 22 = **80 tests**
