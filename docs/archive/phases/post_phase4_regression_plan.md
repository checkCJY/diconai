# Phase 1~4 후속 — 회귀 점검 plan (B/C 트랙)

> **다음 세션 시작 시 이 파일을 가장 먼저 읽기.** Phase 1~4가 모두 완료된 시점에서 모델/시그니처 변경으로 인한 기존 코드 영향을 점검하기 위한 plan. 이전 세션에서 컨텍스트 한계로 작업 중단.

---

## 1. 현재 시점 (2026-05-08)

### Phase 1~4 완료 — 8 commits

| commit | Phase / PR | 핵심 |
|---|---|---|
| `7d2558d` | Phase 1 | 기반 통합 (operations/reference 신설, BaseModel 통일, AlarmType 10종, ActionType 17종) |
| `3abbe16` | Phase 2 | 도메인 모델 (HazardType/AlertPolicy/Notice/VR/Threshold/Menu) |
| `d39fe53` | Phase 3 PR1 | WorkerPosition.received_node FK |
| `b7d23cc` | Phase 3 PR2 | SafetyCheckSection (3단계 마이그) + Event/Notification 확장 |
| `4ecb2a7` | Phase 3 PR3 | SafetyCheckSession + UNIQUE 5단계 마이그 |
| `c2af5c3` | Phase 4 PR1 | threshold_service DB 전환 + 메뉴 DB 조회 + GasData 단일 진실 공급원 |
| `df2ef23` | Phase 4 PR2 | policy_matcher + Django Template 렌더 |
| `c22fd51` | Phase 4 PR3 | DataRetentionPolicy Celery 배치 |

### 검증 누적: 29 단위 테스트 통과, 모든 마이그 reverse 가능, ruff 통과.

### 다음 진행할 트랙
- ❌ **A. 화면 구현** — 사용자가 나중에 화면 사진/명세 받아 진행 (보류)
- ✅ **B. 운영 트랙 + C. 테스트 트랙** — 본 plan에서 진행

---

## 2. 본 plan의 목적

Phase 1~4에서 **모델/필드/시그니처 30+건 변경**됨. 그 과정에서 기존 코드가 깨지지 않았는지 점검 필요. 단위 테스트는 통과했지만 grep 기반 정적 영향 분석 + 핵심 흐름 회귀 테스트로 보강.

---

## 3. 모델 변경 → 잠재 영향 매핑

### 🔴 영향 큼 (확인 필수)

| 변경 | 영향 영역 | 점검 방법 |
|---|---|---|
| **Equipment.equipment_code: `EQP-` → `FAC-`** | 외부 노출 (QR 라벨, CSV, 문서, 프론트 표시), 검색 쿼리 | `grep -rn "EQP-"` 전체 + 프론트 템플릿 |
| **dashboard 메뉴 ID: `SNB-01` → `safety_checklist` 등** | 프론트가 메뉴 ID로 조건 분기/스타일링하면 깨짐 | `grep -rn "SNB-"` JS/template 포함 |
| **Equipment/SafetyCheckItem `deactivate()` 시그니처** | `updated_by` 파라미터 추가 — 모든 호출자가 갱신됐는지 | `grep -rn "\.deactivate(" --include="*.py"` |
| **SafetyStatus `mark_checked()` 시그니처** | `(session, note)` 필수 키워드 | `grep -rn "mark_checked" --include="*.py"` |
| **GasData.save() 위험도 재계산** | fastapi 페이로드 *_risk vs DRF Threshold 재계산 결과 차이 | fastapi `core/gas_thresholds.py` ↔ DRF `facilities/fixtures/threshold_default.json` 1:1 비교 |

### 🟡 영향 중간

| 변경 | 영향 영역 | 점검 방법 |
|---|---|---|
| **AlarmType 4 → 10종** | 기존 코드가 4종만 분기하면 새 타입 미지원 | `grep -rn "AlarmType\." --include="*.py"` switch/if |
| **AlertPolicy seed 미존재 시 동작** | match_policy() → None 반환, fallback OK 확인 | 회귀 테스트 |
| **Notification.event CASCADE → SET_NULL** | 기존 Event 삭제 시 알림 자동 정리 동작 사라짐 | `grep -rn "event\.delete\|notif.*event=None"` |
| **Notification.clean() 강화** | event/policy 둘 다 None 호출은 ValidationError | `grep -rn "Notification\(" --include="*.py"` |
| **POWER_THRESHOLDS 상수 잔존** | dead code인지 다른 곳에서 import하는지 | `grep -rn "POWER_THRESHOLDS"` |
| **LEGAL_THRESHOLDS / FACILITY_THRESHOLDS 제거됨** | 임포트하던 곳 깨짐 | `grep -rn "LEGAL_THRESHOLDS\|FACILITY_THRESHOLDS\|get_legal_threshold"` |

### 🟢 영향 적음 (확인 권장)

| 변경 | 비고 |
|---|---|
| SystemLog 필드 3개 (target_menu/result/target_name) | default 값 → 기존 영향 0 |
| Event.policy/description/status_note | nullable + default → 기존 영향 0 |
| WorkerPosition.received_node | nullable FK → 기존 영향 0 |
| Phase 1/2 신설 모델 | 기존 코드와 무관 |

---

## 4. 진행 방식 (사용자 결정 ✅)

**방식 1 → 방식 3 순으로 진행 결정**:

1. **Step 1**: Explore 에이전트로 §3 영향 영역 일괄 grep → 깨진 호출처/회귀 위험 보고서
2. **Step 2**: 발견된 깨진 곳 즉시 fix (별도 PR)
3. **Step 3**: 핵심 흐름 5개 회귀 테스트 작성 + CI 자동화 (별도 PR)

핵심 흐름 5개 (Step 3):
- 가스 알람 흐름 (페이로드 → GasData.save → 위험도 재계산 → Event/Notification → message 렌더)
- 전력 알람 흐름 (PowerData → power_alarm 전환 → Notification)
- 지오펜스 알람 흐름 (WorkerPosition → 지오펜스 진입 → 알람)
- 안전 체크리스트 (Session 도입 후 check_item)
- 메뉴 트리 (DB 조회 + role 분기)

---

## 5. 다음 세션 첫 작업

### Step 1 진입 — Explore 에이전트 호출

다음 세션 시작 시 아래 프롬프트로 Explore 에이전트 1개 띄우기:

```
diconai 프로젝트의 Phase 1~4 모델 변경에 따른 잠재 영향을 정적 분석해주세요.
docs/phases/post_phase4_regression_plan.md §3 영향 영역 표를 참조해 grep 기반으로
깨진 호출처/회귀 위험을 정리한 보고서를 주세요.

특히 점검할 영역:
1. Equipment.equipment_code "EQP-" → "FAC-" — 모든 사용처 (Python + JS + 템플릿)
2. dashboard 메뉴 ID "SNB-XX" 잔존 — 프론트가 ID로 분기하는 코드
3. .deactivate() 호출자 — Equipment/SafetyCheckItem 모두
4. mark_checked() 호출자 — 시그니처 변경 후 갱신 누락
5. AlarmType.X 분기 코드 — 4종 가정으로 작성됐을 가능성
6. Notification(...) 직접 호출 — clean() 강화 후 event/policy 둘 다 None
7. POWER_THRESHOLDS / LEGAL_THRESHOLDS / FACILITY_THRESHOLDS 임포트
8. fastapi gas_thresholds.py ↔ DRF threshold_default.json fixture 임계치 값 일치 여부

각 항목별로:
- 깨진 호출처 목록 (file:line)
- 위험도 (즉시 깨짐 / 회귀 가능 / 안전)
- 권장 fix 방향

보고서 길이: 1500~3000자.
```

### Step 1 완료 후

- 깨진 호출처 즉시 fix → 별도 commit (`fix : Phase 1~4 회귀 점검 fix`)
- 회귀 위험 항목 정리 → Step 3 회귀 테스트 작성 시 참조

### Step 3 진입 (Step 1/2 완료 후)

핵심 흐름 5개 회귀 테스트 작성. 위치 권장:
- `apps/monitoring/tests/test_gas_alarm_flow.py`
- `apps/monitoring/tests/test_power_alarm_flow.py`
- `apps/positioning/tests/test_geofence_alarm_flow.py`
- `apps/safety/tests/test_check_item_flow.py`
- `apps/dashboard/tests/test_menu_tree.py`

---

## 6. 작업 환경 메모 (다음 세션용)

- **브랜치**: `feature/0508_refactory`
- **커밋 직전 명령어**:
  ```bash
  cd /home/cjy/diconai/drf-server
  .venv/bin/python manage.py check
  .venv/bin/python manage.py makemigrations --dry-run --check
  .venv/bin/python manage.py test <모듈>
  cd /home/cjy/diconai
  pre-commit run --files <변경파일>
  ```
- **commit 메시지 컨벤션**: `타입 : 한 줄 설명` (한글, 50자 이내, github_convention.md)
- **fastapi-server / drf-server 별도 venv** — 작업 위치에 따라 cd 필요

---

## 7. 미해결 항목 (B/C 트랙 외)

회귀 점검 완료 후 다음 우선순위:

### B. 운영 트랙 (남은 항목)
- BaseModel 컨벤션 일괄 통일 PR (15개+ 직접 정의 모델)
- AppLog 비동기 처리 (Celery 큐)
- IntegrationLog batch flush
- DataRetentionPolicy 기본 seed (5종)
- AlertPolicy 기본 seed
- Threshold facility별 정책 (gas_facility_default 그룹)
- GasTypeChoices.LEL dead code cleanup
- POWER_THRESHOLDS 상수 cleanup

### A. 화면 구현 (사용자가 나중에 화면 사진/명세 제공 후 진행)
- 관리자 페이지 CRUD (메뉴/기준정보/공지/알림/안전확인/VR/로그 등)
- 작업자 화면 갱신 (Session 기반 안전 체크리스트, received_node 라벨 등)
- 기존 Phase 4-a 메뉴 트리 사용처 (dashboard/views.py 등)

### 외부 합의 트랙
- 펌웨어 측 node_id 페이로드 (학습 환경에선 더미로 처리됨)
- 피그마 CH4/온도 컬럼 제거 협의

---

## 8. 점검 후 진행 결정 사항 (다음 세션 §4 Step 1 보고서 받은 후)

다음을 결정해야 함:
1. Step 1에서 발견된 깨진 호출처 — 본 PR에서 fix vs 별도 PR
2. Step 3 회귀 테스트 5개 — 모두 한 PR vs 흐름별 분리
3. 발견 위험도에 따라 §7 운영 트랙 우선순위 재조정

---

**다음 세션 입장 멘트 예시**:
> "Phase 1~4 회귀 점검 진행할게요. `docs/phases/post_phase4_regression_plan.md` §5의 Explore 에이전트 프롬프트 그대로 띄워주세요."

---

## 9. 다음 세션 정확성을 높이는 질문 가이드

새 세션의 Claude는 이전 컨텍스트가 없습니다. 정확성을 높이려면 명시적으로 가이드해주세요.

### 9-1. 세션 진입 시 (가장 먼저)

```
이전 세션에서 Phase 1~4를 완료했고, post_phase4_regression_plan.md에 회귀
점검 plan을 남겼습니다. 다음 순서로 진행해주세요:

1. docs/phases/post_phase4_regression_plan.md 전체 먼저 읽기
2. docs/phases/phase_1_plan.md ~ phase_4_pr3_report.md 까지의 보고서들 훑어서
   Phase 1~4에서 무엇이 바뀌었는지 머리에 넣기
3. git log --oneline -10 으로 commit history 확인 (51f8cae 직전 8 commits)
4. 그 후 §5의 Explore 프롬프트로 영향 분석 시작
```

### 9-2. Step 1 (Explore 영향 분석) 보고서 받은 후

```
영향 분석 결과 받았습니다. 다음을 확인해주세요:

A. 발견된 깨진 곳들의 위험도를 다시 분류해주세요:
   - 즉시 깨짐 (현재 import error / 마이그 미적용 / runtime crash)
   - 회귀 가능 (특정 흐름에서만 발현, 평소엔 모름)
   - 컨벤션 불일치 (동작은 하지만 스타일/일관성 문제)

B. fix 작업을 본 PR에 묶을지, 별도 PR로 분리할지 추천 (Phase 1~4와 동일하게
   결정문 형식: 옵션 / 채택 / 장단점).

C. fastapi-server와 drf-server 양쪽 다 영향 받는 항목이 있다면 따로 표시.
   특히 fastapi/core/gas_thresholds.py vs DRF threshold_default.json 임계치
   값 일치 여부는 반드시 확인.
```

### 9-3. Step 2 (fix) 진행 중

```
fix 진행 전 다음을 확인해주세요:

- 각 fix가 Phase 1~4의 결정문/plan에서 정한 컨벤션과 일치하는가?
  (예: BaseModel 직접 정의 패턴 유지, fixture+RunPython 시드 패턴, signal로
  cache invalidate 등)
- fix 후 reverse 검증 가능한가? (마이그 변경 시)
- 기존 단위 테스트 29건이 그대로 통과하는가?
```

### 9-4. Step 3 (회귀 테스트 5개) 진행 중

```
회귀 테스트 작성 전 다음을 결정:

- 단위 테스트 vs 통합 테스트 레벨 — 흐름별 어느 쪽이 적합한가?
  (가스 알람 흐름은 통합 권장, 메뉴 트리는 단위 권장 등)
- 5개를 한 PR에 묶을지 흐름별 분리 PR로 갈지 (Phase 4-ef 패턴 참조)
- pytest 미설치 상태인데 (Phase 1 탐색 보고서) Django TestCase로 충분한지

각 테스트 작성 시 Phase 1~4 보고서의 "변경 내용" 섹션을 다시 읽고
회귀가 발현될 수 있는 케이스를 우선 커버.
```

### 9-5. 마무리 시 (각 PR commit 직전)

```
PR commit 전 다음 자체 검증을 부탁:

- python manage.py check
- python manage.py makemigrations --dry-run --check
- python manage.py test <전체>  (이전 29건 + 새로 추가된 것)
- pre-commit run --files <변경 파일>
- 마이그 추가됐다면 reverse 검증: migrate <app> <이전번호> → migrate <app>
- commit 메시지는 docs/conventions/github_convention.md 컨벤션 (한글, 50자
  이내, 본문은 자유)
- 보고서를 docs/phases/post_phase4_<step>_report.md 형식으로 작성
```

### 9-6. 추가 컨텍스트 명시 (혼동 방지용)

새 세션 Claude가 자주 혼동할 수 있는 점들:

- **`apps.facilities.services.threshold_service`는 Phase 4-d에서 전면 재작성됨** —
  기존 LEGAL_THRESHOLDS / FACILITY_THRESHOLDS 상수 제거. import한 곳 깨졌을 수
  있음.
- **`dashboard/menu.py`도 Phase 4-a에서 전면 재작성됨** — 기존 _MENU_WORKER /
  _MENU_ADMIN_EXTRA dict 제거. ID는 'SNB-XX' → snake_case로 변경.
- **`SafetyStatus.mark_checked()` 시그니처 변경** — `mark_checked(session, note)`
  키워드 인자 필수. 기존 `mark_checked(note=...)` 호출은 깨짐.
- **`Notification.event` CASCADE → SET_NULL** — Event 삭제 시 알림 자동 정리 동작
  사라짐. 단 Soft Delete 정책상 운영 중 Event 삭제는 거의 없음.
- **POWER_THRESHOLDS 상수는 Phase 4 PR1에서 제거 안 됨** — power_alarm.py에서만
  쓰던 import 제거. 다른 곳에서 import 잔존 가능 → grep 필요.
