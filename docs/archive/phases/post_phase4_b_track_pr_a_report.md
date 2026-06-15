# B 운영 트랙 PR-A — fixture 시드 마이그 historical apps 일괄 패턴화

> 작업일: 2026-05-09
> 브랜치: `feature/0508_refactory`
> 부모 plan: [`~/.claude/plans/b-cozy-panda.md`](../../../home/cjy/.claude/plans/b-cozy-panda.md) §3 PR-A
> 직전 단계: 회귀 점검 Step 3 (`b3c24d3`)

---

## 1. 작업 목적

회귀 점검 Step 2에서 발견한 `call_command("loaddata", ...)` 패턴의 fresh migrate 위험을 4개 시드 마이그 일괄 적용. Step 2 fix `0011_seed_threshold_default.py`와 동일 패턴(`apps.get_model().objects.update_or_create()`)으로 historical state 호환 보장. **본 PR은 다른 PR의 마이그가 적층될 기반이 되므로 최선행**.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `manage.py check` | ✅ 통과 |
| 마이그 일관성 | `makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그 reverse + re-apply (4건) | `migrate <app> <prev>` → `migrate <app>` | ✅ 모두 OK |
| pytest 회귀 | `.venv/bin/pytest` | ✅ **56 passed** |
| pre-commit | `pre-commit run --files <변경파일>` | ✅ Passed (ruff-format 자동 정렬 1회 후 통과) |

### 마이그 reverse 검증 흐름 (4건)
```
core:      migrate core 0003 → migrate core         (0004_seed_risk_level_standard)
dashboard: migrate dashboard 0001 → migrate dashboard (0002_seed_menu)
reference: migrate reference 0001 → migrate reference (0002_seed_gas_type)
alerts:    migrate alerts 0004 → migrate alerts     (0005_seed_hazard_type)
```

---

## 3. 변경 파일 (4건)

### 3-1. core/0004_seed_risk_level_standard.py
- 이전: `call_command("loaddata", "risk_level_standard", app_label="core")`
- 이후: 모듈 상수 `RISK_LEVELS` (3 row) + `apps.get_model().objects.update_or_create()`
- fixture json 보존 ([`apps/core/fixtures/risk_level_standard.json`](../../../drf-server/apps/core/fixtures/risk_level_standard.json)) — 수동 loaddata용

### 3-2. dashboard/0002_seed_menu.py
- Menu 12 row (parent self-FK 포함). 부모 row 3건(safety/monitoring/admin_only) 먼저 처리되도록 정렬한 모듈 상수 `MENUS` 정의.
- `parent_id` 사용 (FK 객체 대신 정수) — historical model 호환

### 3-3. reference/0002_seed_gas_type.py
- CodeGroup 1(GAS_TYPE) + CommonCode 10 (lel 포함 — PR-E에서 별도 제거 예정)
- 두 단계 처리 (group → codes)

### 3-4. alerts/0005_seed_hazard_type.py
- HazardTypeGroup 6 + HazardType 10 (AlarmType 1:1)
- `group_id` 정수로 직접 매핑

---

## 4. 사용자 결정 사항 (B-track plan §2)

본 PR은 결정 사항 없음. plan §3 PR-A 그대로 진행.

운영 DB 영향: 모든 마이그가 이미 적용 완료(forward 이미 실행됨)라 본 변경은 **새 환경 fresh migrate에서만 실행**. 기존 운영 데이터 0 영향.

---

## 5. 발견 사항 / 주의

### 5-1. fixture json 보존 정책
재작성 후에도 fixture json 파일은 보존:
- 운영자/관리자 어드민 import용 (`loaddata <app> <fixture>` 수동 실행)
- 재시드/복구 시나리오
- 향후 새 환경 setup 시 reference

마이그가 fixture를 직접 참조하지 않으므로 chart_max 같은 새 필드 추가 시 마이그가 깨지지 않음 (Step 2 fix 0011 동일 효과).

### 5-2. parent_id 직접 사용 (Menu)
historical Menu 모델은 self FK라 `parent` (객체) 대신 `parent_id` (정수)를 defaults에 명시. update_or_create는 부모 row 먼저 생성된 후 자식이 참조 — 모듈 상수 정렬로 보장.

### 5-3. ruff-format 자동 정렬
inline dict 형식이 ruff-format에 의해 multi-line으로 자동 변환됨. 첫 pre-commit 실행 시 2개 파일 (alerts/0005, dashboard/0002) 자동 reformat. 이후 재실행 통과.

---

## 6. 다음 단계

PR-B (BaseModel 컨벤션 10개 모델 일괄 통일) 진입. plan §4 의존 그래프 일관.

---

## 7. 본 PR 외 / 후속

본 PR은 컨벤션 통일 자체 — 동일 패턴은 향후 시드 마이그 추가 시 표준으로 사용.
- PR-C에서 추가될 DataRetentionPolicy/AlertPolicy 시드 마이그도 동일 패턴
- PR-G에서 추가될 gas_facility_default 시드도 동일 패턴
