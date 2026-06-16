# Phase 1~4 + 회귀 점검 + B 운영 트랙 종합 overview

> 작성일: 2026-05-09
> 브랜치: `feature/0508_refactory` (19 commits, main 머지 대기)
> 누적 효과: **84 tests**, DRF 단일 진실 공급원 100%, 컨벤션 정합 완결, 운영 진입 직전 상태

---

## 1. 개요

`feature/0508_refactory` 브랜치에 누적된 19 commits를 한 문서로 정리. 팀원/리뷰어가 빠르게 전체 흐름을 파악할 수 있도록 **아키텍처 + 데이터 흐름**, **의사결정 타임라인**, **검증 방법**에 집중. 상세 작업 내역은 각 phase 보고서 링크 참조.

### 단계 구분 (3 트랙)

| 트랙 | commits | 목적 |
|---|---|---|
| **Phase 1~4 본체** | 8 (`7d2558d` ~ `c22fd51`) | ISH/CJY/imsi/정휘훈 4개 분석 plan을 **계층적**으로 통합 적용 — 기반 → 도메인 → 관계 → 서비스 |
| **회귀 점검 Step 1~3** | 3 (`e81d800` ~ `b3c24d3`) | 모델/시그니처 30+건 변경 후 grep 정적 분석 + POWER_THRESHOLDS DB 일원화 + 27건 회귀 테스트 |
| **B 운영 트랙 PR-A~H** | 8 (`f4b50d0` ~ `d68f56d`) | 운영 진입 직전 잔여 항목 8 PR 일괄 처리 — 컨벤션/시드/비동기 IO/facility 정책/e2e |

**누적 결과**:
- 84 tests (drf-server 62 + fastapi-server 22)
- 모든 마이그 reverse 양방향 검증
- pre-commit (ruff + ruff-format) 통과
- DRF Threshold 단일 진실 공급원 + AlertPolicy 9종 + DataRetentionPolicy 5종 자동 시드

---

## 2. 아키텍처 + 데이터 흐름

[`README.md`](../../../README.md)의 시스템 구조도가 듀얼 서버(DRF + FastAPI) 기본 골격을 설명. 본 작업으로 **추가/변경된 흐름**:

### 2-1. 듀얼 서버 책임 분담

| 서버 | 포트 | 역할 |
|---|---|---|
| [drf-server/](../../../drf-server/) | 8000 | 인증·DB 영속성·REST API·Celery 알람/배치 처리 |
| [fastapi-server/](../../../fastapi-server/) | 8001 | 센서 수신·WebSocket 브로드캐스트·DRF로 fire-and-forget POST |

### 2-2. 알람 흐름 (Phase 4 + B-G/H 통합)

```
센서 페이로드 → FastAPI 수신 → DRF POST (gas/power/positioning)
   ↓
DRF GasData.save()  ─────────────[단일 진실 공급원]
   ↓ recalculate_risks_from_thresholds(facility_id)
   ↓   1순위: gas_facility_default 그룹 (PR-G facility specific)
   ↓   2순위: gas_legal 그룹 (전사 fallback)
   ↓   3순위: NORMAL (graceful)
   ↓
fire_*_alarm_task (Celery)
   ↓ create_alarm_and_event
   ↓   match_policy(event_type, facility_id, …) ── PR-C seed 9종 매칭
   ↓
AlarmRecord + Event(policy=matched) + Notification(message=template render)
   ↓
_push_to_ws → FastAPI /internal/alarms/push/ → WebSocket → 브라우저
   └ IntegrationLog Celery task delay() (PR-D)
```

**핵심 변경**:
- 페이로드의 `*_risk` 필드는 무시 → DRF가 raw 값으로 재계산 (Phase 4-c)
- AlertPolicy 9종 자동 매칭 (PR-C 시드 후 모든 알람 흐름이 정책 매칭)
- facility specific 정책 우선 (PR-G)

### 2-3. 로그 / 운영 IO 흐름 (PR-D)

```
logger.error(...)
   ↓ DBLogHandler.emit (thread-local 재귀 가드)
   ↓ try: applog_create_task.delay(…)   ── Celery worker 비동기
   ↓ except (broker 다운): _sync_insert(…) ── graceful fallback
   ↓
AppLog (web pod 응답 latency 0)

알람 task 완료 후:
   integration_log_create_task.delay(…) ── 동일 패턴
```

### 2-4. 데이터 보관 (Phase 4 PR3)

```
Celery beat (crontab hour=3, minute=0)
   ↓ run_data_retention(dry_run=False)
   ↓
DataRetentionPolicy 5종 순회 (PR-C 시드)
   ↓ is_cycle_due(today) 판정
   ↓
GasData / PowerData / WorkerPosition 보관 기한 초과 row 삭제
```

---

## 3. 의사결정 타임라인

각 단계별 핵심 결정 + 사유. 상세는 [team_decisions_summary.md](team_decisions_summary.md) (Phase 1~4 + 회귀 점검 부분) 및 각 보고서 §결정 사항 섹션 참조.

### 3-1. Phase 1 — 거시 전략 + 인프라

| 결정 | 채택 | 사유 |
|---|---|---|
| 통합 적용 전략 | **B (기반 통합 PR + 도메인 분리)** | Cross-cutting 결정 1 PR 집중 → rebase 충돌 회피 |
| 신규 앱 신설 시점 | **A (operations + reference 동시)** | core 비대화 차단 + ISH/imsi 6 모델 한 번에 분리 |
| AlarmType 10종 | **확장** | CJY 화면 6종 + 정휘훈 4종 통합 |

→ [phase_1_report.md](phase_1_report.md) §5

### 3-2. Phase 2 — 도메인 모델

| 결정 | 채택 | 사유 |
|---|---|---|
| Menu.code 형식 | **snake_case** | 다른 코드값(CodeGroup/RoleProfile) 일관 |
| AppLog 활성 범위 | **ERROR 이상** | 운영 부담 측정 후 LEVEL 확장 |
| IntegrationLog target_system | **자유 텍스트 + 컨벤션 docstring** | validator 강제 X, "FastAPI→DRF" / "GasSensor:GS-001" 두 패턴 |

→ [phase_2_report.md](phase_2_report.md) §5

### 3-3. Phase 3 — 관계 변경 (33 결정)

3a / 3b / 3c / 3d / 3e 5 sub-step. 가장 위험한 3c (SafetyStatus UNIQUE 5단계 마이그)는 별도 PR (PR3) 분리.

→ [phase_3_plan.md](phase_3_plan.md) (33 결정 단독 문서) + [phase_3_pr1~3_report.md](phase_3_pr1_report.md)

### 3-4. Phase 4 — 서비스/뷰 전환

| Sub-step | 작업 |
|---|---|
| 4abcd | Threshold DB + Redis 캐시 + GasData 단일 진실 공급원 + 메뉴 DB 조회 |
| 4ef | AlertPolicy policy_matcher + Notification template_renderer (Django Template) |
| 4g | DataRetentionPolicy Celery 보관 배치 |

→ [phase_4_pr1~3_report.md](phase_4_pr1_report.md)

### 3-5. 회귀 점검 — POWER_THRESHOLDS 일원화

| Step | 결과 |
|---|---|
| Step 1 정적 분석 | 즉시 깨짐 0건, 회귀 가능 1건 (POWER_THRESHOLDS DRF/FastAPI 양측) |
| Step 2 fix | **1A + 2A** 조합: DRF Threshold.chart_max 추가 + alerts/tasks 정리 + FastAPI docstring 강화 |
| Step 3 회귀 테스트 | 5종 흐름 27건 + pytest 도입 (Django TestCase에서 통일) |

→ [post_phase4_step1~3_report.md](post_phase4_step1_report.md)

### 3-6. B 운영 트랙 — 5건 결정 (PR-A~H)

| 결정 | 채택 | 사유 | 반영 PR |
|---|---|---|---|
| 1. AppLog 비동기 | **(b) Celery 큐 + graceful fallback** | Docker/K8s 배포 일관 | PR-D |
| 2. AlertPolicy seed | **(a) 9종 시드 + get_or_create** | 운영자 어드민 수정 보존 + None fallback 의존 해소 | PR-C |
| 3. LEL | **(a) 제거** | 메모리 [sensor_spec_truth_source.md](../../../home/cjy/.claude/projects/-home-cjy-diconai/memory/sensor_spec_truth_source.md) — 센서 정의서 9종에 LEL 없음 | PR-E |
| 4. facility별 Threshold | **(a) 본 plan 포함 (PR-G)** | 작업량 재산정 "중" — 시계열 비대와 무관 | PR-G |
| 5. e2e + 자동 동기화 | **(b) B-10만 본 plan, B-11 별도** | PR-C seed 후 e2e 회귀 가치, B-11은 K8s 결정 후 | PR-H |

→ [post_phase4_b_track_pr_a~h_report.md](post_phase4_b_track_pr_a_report.md) 8건

---

## 4. commits → PR / 문서 매핑

| # | commit | 단계 | 보고서 |
|---|---|---|---|
| 1 | `7d2558d` | Phase 1 기반 통합 | [phase_1_report.md](phase_1_report.md) |
| 2 | `3abbe16` | Phase 2 도메인 모델 | [phase_2_report.md](phase_2_report.md) |
| 3 | `d39fe53` | Phase 3 PR1 (3a) | [phase_3_pr1_report.md](phase_3_pr1_report.md) |
| 4 | `b7d23cc` | Phase 3 PR2 (3b+3d+3e) | [phase_3_pr2_report.md](phase_3_pr2_report.md) |
| 5 | `4ecb2a7` | Phase 3 PR3 (3c) | [phase_3_pr3_report.md](phase_3_pr3_report.md) |
| 6 | `c2af5c3` | Phase 4 PR1 (4abcd) | [phase_4_pr1_report.md](phase_4_pr1_report.md) |
| 7 | `df2ef23` | Phase 4 PR2 (4ef) | [phase_4_pr2_report.md](phase_4_pr2_report.md) |
| 8 | `c22fd51` | Phase 4 PR3 (4g) | [phase_4_pr3_report.md](phase_4_pr3_report.md) |
| 9 | `51f8cae` | 회귀 점검 plan docs | [post_phase4_regression_plan.md](post_phase4_regression_plan.md) |
| 10 | `3791deb` | 회귀 점검 plan §9 | (위 plan 내) |
| 11 | `e81d800` | 회귀 점검 Step 1 | [post_phase4_step1_report.md](post_phase4_step1_report.md) |
| 12 | `eb04045` | 회귀 점검 Step 2 fix | [post_phase4_step2_report.md](post_phase4_step2_report.md) |
| 13 | `b3c24d3` | 회귀 점검 Step 3 | [post_phase4_step3_report.md](post_phase4_step3_report.md) |
| 14 | `f4b50d0` | B 트랙 PR-A | [post_phase4_b_track_pr_a_report.md](post_phase4_b_track_pr_a_report.md) |
| 15 | `7207a4c` | B 트랙 PR-B | [post_phase4_b_track_pr_b_report.md](post_phase4_b_track_pr_b_report.md) |
| 16 | `81e70de` | B 트랙 PR-C | [post_phase4_b_track_pr_c_report.md](post_phase4_b_track_pr_c_report.md) |
| 17 | `cdbeddd` | B 트랙 PR-D | [post_phase4_b_track_pr_d_report.md](post_phase4_b_track_pr_d_report.md) |
| 18 | `af80d69` | B 트랙 PR-E | [post_phase4_b_track_pr_e_report.md](post_phase4_b_track_pr_e_report.md) |
| 19 | `f647d93` | B 트랙 PR-F | [post_phase4_b_track_pr_f_report.md](post_phase4_b_track_pr_f_report.md) |
| 20 | `6acd681` | B 트랙 PR-G | [post_phase4_b_track_pr_g_report.md](post_phase4_b_track_pr_g_report.md) |
| 21 | `d68f56d` | B 트랙 PR-H | [post_phase4_b_track_pr_h_report.md](post_phase4_b_track_pr_h_report.md) |

---

## 5. 검증 방법

각 PR 마무리 시 다음 4단계 통과를 확인 (모든 commit이 동일 절차).

### 5-1. drf-server 검증

```bash
cd /home/cjy/diconai/drf-server
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --dry-run --check
.venv/bin/pytest                  # 62 tests
```

### 5-2. fastapi-server 검증

```bash
cd /home/cjy/diconai/fastapi-server
.venv/bin/pytest                  # 22 tests
```

### 5-3. 마이그 reverse (모델 변경 PR)

```bash
.venv/bin/python manage.py migrate <app> <prev>   # reverse
.venv/bin/python manage.py migrate <app>          # re-apply
```

### 5-4. pre-commit (모든 PR)

```bash
cd /home/cjy/diconai
pre-commit run --files <변경파일>   # ruff + ruff-format
```

### 5-5. 누적 수치
- **drf-server**: 62 tests (단위 + 통합 + e2e + 회귀)
- **fastapi-server**: 22 tests (스모크 + 비동기 mock)
- **마이그 reverse**: PR-A 4건 + PR-B 6건 + PR-C 2건 + PR-E 2건 + PR-G 2건 + Phase 1~4 다단계 모두 양방향 OK
- **pre-commit**: 19 commits 모두 통과

---

## 6. 후속 트랙 (외부 의존성)

| 트랙 | 차단 사유 | 진행 시점 |
|---|---|---|
| **B-11** POWER_THRESHOLDS FastAPI 자동 동기화 | K8s 배포 service discovery 결정 필요 | 인프라 정책 확정 후 |
| **A** 화면 구현 (관리자/작업자 페이지) | 사용자 화면 명세/디자인 수령 필요 | 명세 도착 후 |
| 펌웨어 node_id 페이로드 | 펌웨어팀 합의 필요 | 외부 협의 후 |
| 피그마 CH4/온도 컬럼 협의 | 디자인팀 결정 필요 | 외부 협의 후 |
| AlertPolicy facility별 세부 정책 | 실제 공장별 정책 운영자 결정 필요 | 운영 진입 후 |
| Threshold facility별 row 입력 | 위와 동일 | 운영 진입 후 |
| IntegrationLog batch endpoint | 호출 빈도 측정 필요 | 운영 진입 후 |

본 브랜치는 **즉시 main 머지 가능** — 외부 의존 항목은 모두 운영 진입 후 또는 외부 합의 후로 분리.

---

## 7. 참조 문서 인덱스

### 7-1. Phase plan/report (12개)
- [phase_1_plan.md](phase_1_plan.md) / [phase_1_report.md](phase_1_report.md)
- [phase_2_plan.md](phase_2_plan.md) / [phase_2_report.md](phase_2_report.md)
- [phase_3_plan.md](phase_3_plan.md) (33 결정 단독) / [phase_3_pr1_report.md](phase_3_pr1_report.md) / [phase_3_pr2_report.md](phase_3_pr2_report.md) / [phase_3_pr3_report.md](phase_3_pr3_report.md)
- [phase_4_plan.md](phase_4_plan.md) / [phase_4_pr1_report.md](phase_4_pr1_report.md) / [phase_4_pr2_report.md](phase_4_pr2_report.md) / [phase_4_pr3_report.md](phase_4_pr3_report.md)

### 7-2. 회귀 점검 (4개)
- [post_phase4_regression_plan.md](post_phase4_regression_plan.md)
- [post_phase4_step1_report.md](post_phase4_step1_report.md) / [post_phase4_step2_report.md](post_phase4_step2_report.md) / [post_phase4_step3_report.md](post_phase4_step3_report.md)

### 7-3. B 운영 트랙 (8개)
- [post_phase4_b_track_pr_a_report.md](post_phase4_b_track_pr_a_report.md) ~ [post_phase4_b_track_pr_h_report.md](post_phase4_b_track_pr_h_report.md)

### 7-4. 결정 통합 (1개)
- [team_decisions_summary.md](team_decisions_summary.md) — Phase 1~4 + 회귀 점검까지 (B 트랙 결정은 본 overview §3-6 참조)

### 7-5. 프로젝트 메인
- [README.md](../../../README.md) — 프로젝트 소개 + 기술 스택 + 시스템 구조도 PNG
- [CLAUDE.md](../../../.claude/CLAUDE.md) — 작업 규칙 + 컨벤션
- [docs/conventions/](../../conventions/) — dev_convention / github_convention / COMMANDS

---

## 8. 본 overview의 위치

본 문서는 **19 commits 종합 reference**. 사용 시나리오:
- 신규 합류자 온보딩 — §2 아키텍처 + §3 결정 타임라인
- 리뷰어 — §4 commits 매핑 + §5 검증 방법
- 운영 진입 직전 — §6 후속 트랙으로 외부 의존 항목 식별
- main 머지 PR — 본 overview를 PR 본문 reference로 첨부

추후 새 트랙(B-11/화면/펌웨어 합의) 진입 시 동일 형식의 overview 추가 권장.
