# CHANGES_REVIEW — `feature/0508_refactory_code` 변경 내용 종합

> **47 commits · 317 files · +24,698 / −479** (코드 219 / 문서 98)
> 작업일: 2026-05-08 ~ 2026-05-11
>
> PR 리뷰어·팀원이 한 페이지에서 **전체 변경 윤곽** 을 잡고 → 자기 관심 영역으로 **commit/파일/상세 doc 으로 drill-down** 하기 위한 종합 진입 문서.

---

## 1. 한 줄 요약

> Phase 1~4 도메인 모델 대수술 → 회귀 점검 → 운영 안정화(B 트랙) → 보안/JS 정합(J 트랙) → 문서화. 모든 보안 변경은 **옵트인 — env 미설정 시 기존 동작 회귀 0**.

| 항목 | 수치 |
|---|---|
| 커밋 | 47 |
| 변경 파일 | 317 (코드 219 / 문서 98) |
| 라인 변동 | +24,698 / −479 (코드만 +9,190 / −453) |
| 신규 테스트 | drf 33 + fastapi 22 + e2e 4 = **59건** |
| 신규 문서 | 53개 (이 문서 포함) |
| 작업 기간 | 2.5일 + 후속 1일 |

---

## 2. 카테고리별 변경 인벤토리

### A. 도메인 모델 (Phase 1~3 + B 트랙 모델 정합)

| # | 변경 | commit | 핵심 파일 | 영향 | 상세 |
|---|---|---|---|---|---|
| A.1 | **Phase 1 기반** — `operations`·`reference` 앱 신설 + `BaseModel` 도입 + AlarmType 10종 확장 | `7d2558d` | `apps/operations/`, `apps/reference/`, `apps/core/models/base.py`, `apps/core/constants.py` | 어드민에 운영로그·공통코드 메뉴 등장. BaseModel 상속 모델은 자동 `created_at/updated_at/updated_by` | [phase_1_report.md](../../../phases/phase_1_report.md) |
| A.2 | **Phase 2 도메인** — HazardType/AlertPolicy/Notice/VR 6개 도메인 모델 신설 | `3abbe16` | `apps/alerts/models/`, `apps/notices/`, `apps/training/`, `apps/dashboard/` | 운영자가 어드민에서 알림 정책·위험 유형 등 편집 가능 | [phase_2_report.md](../../../phases/phase_2_report.md) |
| A.3 | **Phase 3 PR1** — WorkerPosition.received_node FK 추가 | `d39fe53` | `apps/positioning/models/worker_position.py` | 어떤 위치 노드가 좌표 수신했는지 추적 가능 | [phase_3_pr1_report.md](../../../phases/phase_3_pr1_report.md) |
| A.4 | **Phase 3 PR2** — SafetyCheckSection + Event/Notification 확장 (3단계 마이그) | `b7d23cc` | `apps/safety/models/`, `apps/alerts/models/event.py` | 체크리스트 항목 그룹화. Event 에 description/status_note 추가 | [phase_3_pr2_report.md](../../../phases/phase_3_pr2_report.md) |
| A.5 | **Phase 3 PR3** — SafetyCheckSession + Revision + UNIQUE 5단계 마이그 | `4ecb2a7` | `apps/safety/models/safety_check_session.py`, `safety_checklist_revision.py` | 1일 1세션 단위 + 발행 시점 동결 스냅샷. 매일 체크 가능 | [phase_3_pr3_report.md](../../../phases/phase_3_pr3_report.md) |
| A.6 | **B 트랙 PR-A** — fixture 시드 마이그 historical apps 패턴 통일 (4 앱) | `f4b50d0` | `apps/{core,dashboard,reference,alerts}/migrations/` | loaddata → `update_or_create` idempotent 시드 표준 | [PR-A 보고서](../../../phases/post_phase4_b_track_pr_a_report.md) |
| A.7 | **B 트랙 PR-B** — BaseModel 컨벤션 10개 모델 일괄 통일 | `7207a4c` | 10개 model + 6개 마이그 | 도메인 모델 전반에 이력 추적 컬럼 통일 | [PR-B 보고서](../../../phases/post_phase4_b_track_pr_b_report.md) |
| A.8 | **B 트랙 PR-C** — 기본 시드 (DataRetentionPolicy 5종 + AlertPolicy 9종) | `81e70de` | 2개 마이그 시드 | 신규 시스템 구동 즉시 알림 매칭/보관 정책 동작 | [PR-C 보고서](../../../phases/post_phase4_b_track_pr_c_report.md) |
| A.9 | **B 트랙 PR-E** — GasTypeChoices.LEL dead code 제거 | `af80d69` | `apps/core/constants.py`, fixture | 센서 정의서 9종과 100% 일치 | [PR-E 보고서](../../../phases/post_phase4_b_track_pr_e_report.md) |

→ 신규 모델 28개, 신규 앱 5개 (`dashboard/notices/operations/reference/training`). 모델 인벤토리 상세는 [skill/DB/DB 변경사항_최재용.md](../../../../skill/DB/DB%20변경사항_최재용.md) (로컬 only — gitignored).

### B. 알림·이벤트 시스템 (Phase 4)

| # | 변경 | commit | 핵심 파일 | 영향 | 상세 |
|---|---|---|---|---|---|
| B.1 | **Phase 4 PR1** — 임계치/메뉴 DB 인프라 (4a~4d) | `c2af5c3` | `apps/alerts/services/threshold_service.py`, `apps/dashboard/views.py` | 가스/전력 임계치가 상수 → DB `Threshold` 모델. 메뉴 `get_menu_tree(role)` DB 조회 전환 | [phase_4_pr1_report.md](../../../phases/phase_4_pr1_report.md) |
| B.2 | **Phase 4 PR2** — AlertPolicy 매칭 + Notification 템플릿 (4e+4f) | `df2ef23` | `apps/alerts/services/policy_matcher.py`, `template_renderer.py` | Event 발생 → 매칭 정책 검색 → Notification 자동 생성 + Django Template 메시지 렌더 | [phase_4_pr2_report.md](../../../phases/phase_4_pr2_report.md) |
| B.3 | **Phase 4 PR3** — DataRetentionPolicy Celery 보관 배치 (4g) | `c22fd51` | `apps/operations/tasks/data_retention_task.py` | 5종 정책별 자동 정리 (가스 원천/이상, 전력 원천/집계, 위치 이력) | [phase_4_pr3_report.md](../../../phases/phase_4_pr3_report.md) |
| B.4 | **B 트랙 PR-G** — Threshold facility별 정책 + `gas_facility_default` 시드 | `6acd681` | `apps/facilities/models/thresholds.py`, 마이그 시드 | facility specific 임계치 우선 적용 → legal fallback. 어드민에서 시설별 임계치 편집 | [PR-G 보고서](../../../phases/post_phase4_b_track_pr_g_report.md) |
| B.5 | **회귀 점검 Step 2** — POWER_THRESHOLDS DB 일원화 + chart_max 필드 | `eb04045` | `apps/facilities/models/thresholds.py`, `core/constants.py` | 전력 임계치도 DB 단일 진실 공급원. 차트 Y축 어드민 조정 가능 | [Step 2 보고서](../../../phases/post_phase4_step2_report.md) |

### C. 보안·인증 (Phase 5 옵트인 — env 미설정 시 비활성)

| # | 변경 | commit | 핵심 파일 | 영향 | 상세 |
|---|---|---|---|---|---|
| C.1 | **B6-B8** — SimpleJWT blacklist + ROTATE + access lifetime 1h | `4735670` | `config/settings.py`, `INSTALLED_APPS` | `JWT_ACCESS_TOKEN_LIFETIME_HOURS=1` 권장. 기존 refresh 토큰 1회 사용 후 무효화 | [wave_2.md](wave_2.md) |
| C.2 | **B9** — LogoutView refresh 토큰 블랙리스트 | `3567c60` | `apps/accounts/views/auth_views.py` (LogoutView) | 로그아웃 시 서버 측 refresh 즉시 무효화 | [wave_2.md](wave_2.md) |
| C.3 | **B11** — fastapi JWT 검증 인프라 + drf SIGNING_KEY 명시 | `39d2ba7` | `fastapi-server/websocket/auth.py` (신규), `core/config.py` | WS 인증 옵트인 인프라. PyJWT 2.10.1 추가 | [wave_3.md](wave_3.md) |
| C.4 | **B12** — WS 엔드포인트 인증 (`/ws/sensors/`, `/ws/worker/{id}/`) | `947cbc8` | `fastapi-server/websocket/routers/ws_router.py` | `JWT_SIGNING_KEY` 설정 시 WS query token 검증 활성 | [wave_3.md](wave_3.md) |
| C.5 | **B3+B4** — service token authentication (ingest endpoints) | `00ae07c` | `apps/core/authentication.py` (신규), 5개 view, `apps/alerts/tasks.py`, fastapi `alarm_router.py` | `INTERNAL_SERVICE_TOKEN` 양쪽 설정 시 ingest + alarm-push 인증 | [wave_1.md §B3+B4](wave_1.md), [99_security_summary.md](../../../codereviews/2026_05_09/99_security_summary.md) |

> ⚠️ **양쪽 동일 값 필수** — 한쪽만 켜면 통신 차단. 활성화 절차: [TEAM_BRIEF §6](TEAM_BRIEF.md), [MIGRATION_GUIDE Step 3~5](MIGRATION_GUIDE.md).

### D. JS 프론트엔드 (J 트랙 + Wave 4)

| # | 변경 | commit | 핵심 파일 | 영향 | 상세 |
|---|---|---|---|---|---|
| D.1 | **J1-J4** — JS 정합 (levelLabel 제거 / pushData 검증 / WS_BASE 가드 / pad 중복 제거) | `eb60cfc` | `static/js/shared/{util,config,ws-client}.js`, `detail/safety_history.js` | dead code 제거 + 운영 환경 가드 + 중복 정의 정리 | [wave_1.md J1-J4](wave_1.md) |
| D.2 | **J5-J8** — JS 로깅·layout 가드 (WSClient warn / iconMap warn / ROLE_LABEL 상수 / handleRefresh 누적 방지) | `0b67e7c` | `static/js/shared/{ws-client,layout}.js` | 운영 가시성 향상 + setTimeout 누수 방지 | [wave_1.md J5-J8](wave_1.md) |
| D.3 | **J9-J11** — JS 에러 핸들링 (initApp catch / loadMySafetyStatus warn / Auth.getMe warn) | `5ee7628` | `static/js/dashboard/app.js`, `shared/auth.js` | unhandled rejection 차단 + 401 시 로그 가시화 | [wave_1.md J9-J11](wave_1.md) |
| D.4 | **J12+J13** — Auth._refresh 싱글톤 + Logout body refresh 동봉 | `c58373d` | `static/js/shared/auth.js` | 다중 401 race 차단 (in-flight Promise 가드) + 서버 블랙리스트 호환 | [wave_2.md J12+J13](wave_2.md) |
| D.5 | **J17** — ws-client 호출자 attachToken 일관 적용 (8곳) | `f8edd2d` | 8개 WS 호출자 | 전 페이지 WS 토큰 부착 일관성 | [wave_3.md J17](wave_3.md) |
| D.6 | **Wave 4** — JS [상] 권고 후속 7건 (백오프/매퍼/Menu/AlarmPopup/timestamp/level-mapper) | `a74c896` | `ws-client.js`, `alarm-mapper.js` (신규), `level-mapper.js` (신규), `alarm-popup.js`, `layout.js`, `app.js`, 4 templates | WS 지수 백오프 + 알람 매핑 단일화 + XSS 패턴 + 큐 그룹핑 + 서버 timestamp + RiskLevel 변환층 | [wave_4.md](wave_4.md) |

→ JS 권고 60건 중 **24건 적용** (J 트랙 17 + Wave 4 의 7). Top 10 중 9 적용. 미적용 1건 (02 R3 catch-up) 은 [§6](#6-남은-후속-별도-pr) 참조.

### E. 운영·인프라 (B 트랙 + 테스트)

| # | 변경 | commit | 핵심 파일 | 영향 | 상세 |
|---|---|---|---|---|---|
| E.1 | **B1** — print() → logger.exception (positioning) | `b6cb6ce` | `apps/positioning/views/position_views.py` | Sentry 등 로그 수집 도구로 traceback 전파 | [wave_1.md B1](wave_1.md) |
| E.2 | **B2** — AlarmPayload extra="allow" → "ignore" | `0770423` | `fastapi-server/internal/routers/alarm_router.py` | 미정의 필드 silent drop (보안·정합성 향상) | [wave_1.md B2](wave_1.md) |
| E.3 | **B5** — WorkerSummaryView permission_classes 클래스화 | `7e6b404` | `apps/alerts/views/alarm_record.py` | DRF 권한 컨벤션 일관 | [wave_1.md B5](wave_1.md) |
| E.4 | **PR-D** — AppLog/IntegrationLog Celery 비동기 INSERT | `cdbeddd` | `apps/operations/tasks/`, `log_handlers.py` | web pod latency 0 (큐 처리). broker 다운 시 graceful fallback | [PR-D 보고서](../../../phases/post_phase4_b_track_pr_d_report.md) |
| E.5 | **PR-F** — fastapi-server pytest 인프라 + 스모크 22건 | `f647d93` | `fastapi-server/tests/`, `pytest.ini` | fastapi 측 회귀 검증 가능 | [PR-F 보고서](../../../phases/post_phase4_b_track_pr_f_report.md) |
| E.6 | **PR-H** — e2e 알람 흐름 통합 테스트 4건 | `d68f56d` | `drf-server/apps/alerts/tests/test_e2e_*.py` | 센서 페이로드 → DRF → Celery → fastapi WS 전 구간 | [PR-H 보고서](../../../phases/post_phase4_b_track_pr_h_report.md) |
| E.7 | **회귀 Step 3** — Phase 1~4 회귀 테스트 5종 + pytest 도입 | `b3c24d3` | drf-server/apps/{alerts,monitoring,safety,...}/tests/ | 단위 테스트 29 → 62건 (33건 추가). pytest 표준화 | [Step 3 보고서](../../../phases/post_phase4_step3_report.md) |

---

## 3. 마이그레이션 영향 요약

| 항목 | 변경 |
|---|---|
| drf-server 마이그 추가 | Phase 1~4 + B 트랙 PR-A~G + token_blacklist 13개 |
| 신규 테이블 | 28개 (BaseModel/AlertPolicy/Threshold/Menu/Notice/VRTraining/Section/Session/Revision 등) |
| FK 추가 | `WorkerPosition.received_node`, `Department.company/parent/leader`, `Event.policy`, `Notification.policy` 외 |
| FK 제거 | `CustomUser.department` (UserDepartment M:N 으로 이전) |
| UNIQUE 변경 | `SafetyStatus.UNIQUE(worker, check_item)` → `(session, check_item)` (5단계 마이그) |
| 시드 자동 추가 | AlertPolicy 9종, DataRetentionPolicy 5종, Threshold default groups, gas_facility_default |
| 비가역 마이그 | `token_blacklist` 13개 — **운영 적용 시 백업 후 진행** |

> 마이그 reverse 검증: 모든 마이그가 `migrate {app} 000N` 명령으로 한 단계 롤백 가능 (단 token_blacklist 는 비가역).

---

## 4. PR 리뷰어 체크리스트

### 구조 (마이그·시드)
- [ ] `python manage.py migrate` 무사 적용 (drf 마이그 + token_blacklist 13)
- [ ] 마이그 reverse 검증 (`python manage.py migrate --plan` 으로 마이그 트리 확인)
- [ ] `AlertPolicy` 9종 / `DataRetentionPolicy` 5종 / `Threshold` 기본 그룹 시드 자동 적용
- [ ] BaseModel 상속 11개 모델의 `updated_by` FK NULL 허용 (작업자 탈퇴 보전)

### 기능 (자동 테스트)
- [ ] `cd drf-server && python -m pytest -q` → **62 passed**
- [ ] `cd fastapi-server && python -m pytest -q` → **22 passed**
- [ ] 회귀 테스트 27건 (Phase 1~4 + B 트랙) 모두 PASS

### 옵트인 (회귀 0 보장)
- [ ] `INTERNAL_SERVICE_TOKEN=""` 시 ingest 무인증 통과 (기존 동작)
- [ ] `JWT_SIGNING_KEY=""` 시 WS 무인증 통과 (기존 동작)
- [ ] env 양쪽 동일 값 설정 시 ingest/WS 인증 동작 (수동 테스트: `wscat` 토큰 없이 → close 1008)
- [ ] `JWT_ACCESS_TOKEN_LIFETIME_HOURS` 활성화 시 1~4h 권장 (기본 24)

### JS 프론트엔드
- [ ] `alarm-mapper.js` 가 4 템플릿 (`dashboard/main`, `snb_details/{event_detail,monitoring_events,monitoring_realtime}`) 에 일관 위치 삽입
- [ ] `level-mapper.js` 가 `dashboard/websocket.js` 의 `_riskClass` 대체 (로컬 매핑 잔존 0)
- [ ] WS 백오프 — 강제 종료 후 콘솔에서 1s → 2s → 4s → ... → 30s 간격 확인
- [ ] `Menu.render` — DOM 검사로 `menu.label`/`child.label` 가 textContent 처리됨
- [ ] AlarmPopup 같은 센서 5초 내 연속 알람 → `(×N)` 그룹핑 표시

### 문서·링크
- [ ] [TEAM_BRIEF §2-bis](TEAM_BRIEF.md) cheatsheet 적용 명령 정확
- [ ] [README .env 표](../../../../README.md) `INTERNAL_SERVICE_TOKEN` / `JWT_SIGNING_KEY` / `JWT_ALGORITHM` 등장
- [ ] README docs/ 링크 broken 0건

---

## 5. 이미 검증된 항목 (자동 통과)

- ✅ **drf 62 + fastapi 22 = 84 tests green** (회귀 0)
- ✅ Node 문법 검사 모든 신규/수정 JS 파일 OK (`ws-client` / `alarm-mapper` / `level-mapper` / `alarm-popup` / `alarm-ws` / `worker-ws` / `dashboard/websocket` / `dashboard/app` / `layout`)
- ✅ pre-commit hook 통과 (ruff / ruff-format / trailing-whitespace / end-of-file-fixer)
- ✅ ruff lint+format clean (drf-server + fastapi-server)
- ✅ broken 링크 정정 — README docs/ 6건 (specs/conventions 폴더로 이전 반영)
- ✅ 회귀 점검 Step 1 정적 분석 — 즉시 깨짐 0건 / 회귀 가능 1건 (Step 2 fix 완료)

---

## 6. 남은 후속 (별도 PR)

| 항목 | 사유 | 추정 sprint |
|---|---|---|
| **02 R3** WS 메시지 catch-up (last_event_id) | 서버 ring buffer 설계 필요 — 메모리 상한 / 재시작 시 buffer 손실 정책 / `last_event_id` 위변조 방지 / 다중 fastapi 인스턴스 sync | 다음 sprint |
| **05 R3 옵션 A** — CSS 클래스 일괄 리네임 (`caution`→`warning`, `safe`→`normal`) | 10+ CSS 파일 + 마크업 + 다른 JS 분산 매핑 동시 정리. 옵션 B(매퍼)는 이번에 적용 완료 | 다음 sprint |
| **04 R2** — initHeaderAndSNB getMe 실패 처리 | 인증 만료 vs 네트워크 실패 구분 UX 정책 결정 필요 | UX 협의 후 |
| **.github/PULL_REQUEST_TEMPLATE.md** | github_convention.md 의 PR 양식 자동 로드 | 선택 |
| **JS 권고 [중]/[하]** ~33건 | 운영 진입에 시급하지 않음 | 다음 정리 sprint |

---

## 7. 상세 가이드 진입점

### 적용·머지
- **빠른 적용 (5분):** [TEAM_BRIEF §2-bis](TEAM_BRIEF.md) — pull 후 4단계 명령
- **머지·운영 상세:** [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) — Step 1~5 + 트러블슈팅 + 옵트인 활성화 매트릭스
- **Phase 5 옵트인 활성화:** [TEAM_BRIEF §6](TEAM_BRIEF.md)

### 변경 사유·설계
- **Wave 1~4 실행 보고서:** [wave_1.md](wave_1.md) (정합·로깅) / [wave_2.md](wave_2.md) (JWT 보안) / [wave_3.md](wave_3.md) (WS 인증) / [wave_4.md](wave_4.md) (JS [상] 후속)
- **Phase 1~4 보고서:** [phase_1_report.md](../../../phases/phase_1_report.md) ~ [phase_4_pr3_report.md](../../../phases/phase_4_pr3_report.md) (8개)
- **B 트랙 PR-A~H:** [post_phase4_b_track_pr_a~h_report.md](../../../phases/) (8개)
- **회귀 점검:** [post_phase4_regression_plan.md](../../../phases/post_phase4_regression_plan.md) + Step1~3 보고서

### 코드리뷰·분석
- **도메인별 코드리뷰 11종:** [codereviews/2026_05_09/](../../../codereviews/2026_05_09/) (01_auth ~ 09_realtime + 99_security)
- **JS 함수 단위 분석 7종:** [refactor/js/2026_05_09/](../../js/2026_05_09/) (00_overview + 01~06)
- **의사결정 통합:** [team_decisions_summary.md](../../../phases/team_decisions_summary.md) (33+건 옵션·채택·근거)

---

## 8. 빠른 적용 명령

```bash
# 1) pull 후 의존성
cd drf-server     && uv pip install -r requirements.txt && cd ..
cd fastapi-server && uv pip install -r requirements.txt && cd ..

# 2) DB 마이그레이션 (drf 만)
cd drf-server && python manage.py migrate

# 3) 검증
python -m pytest -q                          # 62 passed
cd ../fastapi-server && python -m pytest -q  # 22 passed

# 4) 양 서버 + Celery 재시작
```

신규 .env 변수 (모두 옵트인 — 빈 값 = 비활성):

| 변수 | drf | fastapi | 효과 |
|---|:---:|:---:|---|
| `INTERNAL_SERVICE_TOKEN` | ✅ | ✅ | drf ingest + fastapi alarm-push 양방향 토큰 |
| `JWT_SIGNING_KEY` | ✅ | ✅ | WS JWT 검증 (drf SIGNING_KEY와 동일 값) |
| `DRF_SERVICE_TOKEN` | — | ✅ | fastapi → drf 호출 시 헤더 부착 (= INTERNAL_SERVICE_TOKEN) |
| `JWT_ACCESS_TOKEN_LIFETIME_HOURS` | ✅ | — | 기본 24, 활성화 시 1~4 권장 |

**작동 시 주의점 4가지:**
1. **마이그 비가역** — `token_blacklist` 13개. 운영 적용 시 백업 후
2. **기존 refresh 토큰 재로그인 필요** — `ROTATE_REFRESH_TOKENS=True` 활성 시. 사전 공지
3. **양 서버 + Celery 동시 재시작** — 옵트인 켤 때 한쪽만 재시작 시 통신 끊김
4. **WS access log token 노출 가능** — `?token=...` 쿼리. 운영 시 access log filter 권장

상세는 [TEAM_BRIEF §2-bis · §6](TEAM_BRIEF.md) / [MIGRATION_GUIDE](MIGRATION_GUIDE.md) 참조.
