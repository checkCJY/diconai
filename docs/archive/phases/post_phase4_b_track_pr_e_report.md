# B 운영 트랙 PR-E — GasTypeChoices.LEL dead code 제거

> 작업일: 2026-05-09
> 브랜치: `feature/0508_refactory`
> 부모 plan: [`~/.claude/plans/b-cozy-panda.md`](../../../home/cjy/.claude/plans/b-cozy-panda.md) §3 PR-E
> 직전 PR: [post_phase4_b_track_pr_d_report.md](post_phase4_b_track_pr_d_report.md) (`cdbeddd`)

---

## 1. 작업 목적

센서 정의서(2026-04-01) 9종에 LEL 미포함 — `GasTypeChoices.LEL`은 dead code 상태. 메모리 `sensor_spec_truth_source.md` 결정 따라 제거. CI 정합성(`GasTypeChoices` ↔ `CommonCode(GAS_TYPE)` 1:1) 자동 유지.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `manage.py check` | ✅ 통과 |
| 마이그 일관성 | `makemigrations` | ✅ alerts.0010 자동 생성 (gas_type choices 갱신) |
| 마이그 적용 | `migrate` | ✅ alerts.0010 + reference.0003 OK |
| 마이그 reverse + re-apply | 양쪽 reverse → forward | ✅ OK |
| LEL 제거 검증 | shell — `CommonCode.objects.filter(code='lel').count()` | ✅ 0 (CommonCode 9 row) |
| pytest 회귀 | `.venv/bin/pytest` | ✅ **56 passed** (CI 정합성 `test_gas_type_consistency` 자동 통과) |
| pre-commit | `pre-commit run --files <변경파일>` | ✅ Passed |

---

## 3. 변경 파일

### 3-1. 신규 마이그 (2개)

| 파일 | 역할 |
|---|---|
| [apps/alerts/migrations/0010_alter_alarmrecord_gas_type.py](../../../drf-server/apps/alerts/migrations/0010_alter_alarmrecord_gas_type.py) | `AlarmRecord.gas_type` choices를 9종으로 갱신 (자동 생성 — GasTypeChoices 변경 detect) |
| [apps/reference/migrations/0003_remove_lel.py](../../../drf-server/apps/reference/migrations/0003_remove_lel.py) | RunPython — `CommonCode(group=GAS_TYPE, code=lel)` row 삭제. reverse는 row 복원 |

### 3-2. 기존 수정 (4개)

| 파일 | 변경 |
|---|---|
| [apps/core/constants.py](../../../drf-server/apps/core/constants.py) | `GasTypeChoices.LEL` 라인 제거 (9종으로 축약). docstring 갱신 (PR-E 변경 사실 + 메모리 근거 명시) |
| [apps/reference/fixtures/gas_type.json](../../../drf-server/apps/reference/fixtures/gas_type.json) | pk=10 LEL row 제거, CodeGroup description "9종"으로 갱신 |
| [apps/reference/migrations/0002_seed_gas_type.py](../../../drf-server/apps/reference/migrations/0002_seed_gas_type.py) | PR-A에서 작성한 seed에서 LEL 제거 (fresh migrate 시 9종 시드) + docstring PR-E 변경 명시 |
| [apps/facilities/services/threshold_service.py](../../../drf-server/apps/facilities/services/threshold_service.py) | `evaluate_gas_risk` docstring에서 "lel은 임계치 미정의" 라인 제거 — GasTypeChoices에서 LEL 제거됐으므로 무의미 |

---

## 4. 사용자 결정 사항 (B-track plan §2 결정 3)

| 항목 | 채택 | 본 PR 반영 |
|---|---|---|
| GasTypeChoices.LEL | (a) 제거 | ✅ enum + fixture + 시드 + 마이그 모두 정리 |
| 메모리 근거 | `sensor_spec_truth_source.md` — 센서 정의서 9종에 LEL 없음 | ✅ docstring에 명시 |

---

## 5. 발견 사항 / 주의

### 5-1. CI 정합성 자동 유지
[apps/reference/tests/test_gas_type_consistency.py](../../../drf-server/apps/reference/tests/test_gas_type_consistency.py)의 `test_gas_type_enum_matches_common_code`가 `GasTypeChoices.values` ↔ `CommonCode(GAS_TYPE).code` 1:1 일치 검증. PR-E에서 양측 동시 9종으로 줄이므로 자동 통과 — 실패 없음.

### 5-2. AlarmRecord.gas_type historical row 호환
운영 DB에 `AlarmRecord.gas_type='lel'`인 historical row가 있다면, 모델 choices가 9종으로 줄어도 DB CharField는 값 유지 (Django choices는 입력 검증용, 기존 row는 영향 없음). 단 어드민 화면에서는 "lel" 표시명이 빈 값으로 보일 수 있음. 학습 환경에서는 0건.

### 5-3. Threshold/모델 컬럼 영향 0
- `facilities.Threshold(group=gas_legal)` — LEL 임계치 row 없음 (Step 2 fix `0011_seed_threshold_default.py` 9종만 시드)
- `monitoring.GasData` — 가스 9종 컬럼만 보유 (LEL 컬럼 없음)
- `_recalculate_risks_from_raw` — 9종 처리 → 변경 0

→ 모든 운영 흐름이 9종으로 일관. PR-E는 enum/CommonCode 정리만으로 충분.

### 5-4. raw_payload 호환
[apps/monitoring/serializers/gas_data.py](../../../drf-server/apps/monitoring/serializers/gas_data.py)는 fastapi 페이로드의 lel 키를 `raw_payload`에 보관 (모델 컬럼 미저장). 기존 historical row의 raw_payload에 lel 값 있어도 무시됨 → 영향 0.

---

## 6. 다음 단계

PR-F (fastapi-server pytest 인프라) 진입. 본 PR은 drf-server 독립 변경. PR-F는 fastapi-server 독립 트랙으로 PR-A~E와 무관하게 진행.

---

## 7. 누적 결과

| PR | commit | 변경 |
|---|---|---|
| PR-A | `f4b50d0` | fixture 시드 마이그 historical apps 패턴 |
| PR-B | `7207a4c` | BaseModel 컨벤션 10개 모델 |
| PR-C | `81e70de` | DataRetentionPolicy + AlertPolicy 시드 |
| PR-D | `cdbeddd` | AppLog/IntegrationLog Celery 비동기 |
| **PR-E** | (본 commit) | GasTypeChoices.LEL dead code 제거 |
