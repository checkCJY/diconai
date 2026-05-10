# TEAM_BRIEF — `feature/0508_refactory_code` 브랜치 공유

> **작성:** 2026-05-10 · **대상:** 팀원 전체 (개발자 중심) · **목적:** PR 받는 즉시 5분 안에 맥락을 따라잡기 위한 단일 진입 문서

`origin/main` 대비 **42 commits / 317 파일 / +24,698 −479** 의 대형 리팩토링입니다. 문서가 52개 작성되어 있어 정보가 부족한 게 아니라 **"무엇을 어떤 순서로 봐야 하는지"** 가 막막한 상태라 이 문서를 만들었습니다.

---

## 1. 한 줄 요약

> **Phase 1~4 도메인 모델 대수술 → 회귀 점검 → 운영 안정화 → 보안/JS 정합 → 문서화.**
> 단계마다 직전 단계의 변경이 안전한지 검증·보강하는 **다층 검증** 구조.

---

## 2. 규모

| 항목 | 수치 |
|---|---|
| 커밋 | 42 |
| 변경 파일 | 317 (코드 219 / 문서 98) |
| 라인 변동 | +24,698 / −479 (코드만 +9,190 / −453) |
| 신규 테스트 | drf 33건 + fastapi 22건 + e2e 4건 = **59건** |
| 신규 문서 | 51개 / 51,234 라인 |
| 작업 기간 | 2026-05-08 ~ 2026-05-10 (약 2.5일) |

---

## 2-bis. 5분 Apply Cheatsheet — 팀원 즉시 적용용

> 이 섹션만 보고도 머지 후 적용 끝낼 수 있도록 정리. 상세 옵션·문제 해결은 §6 / [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md).

### 적용 명령 (pull 후 4단계)

```bash
# 1) 의존성 갱신 (drf + fastapi 양쪽)
cd drf-server      && uv pip install -r requirements.txt && cd ..
cd fastapi-server  && uv pip install -r requirements.txt && cd ..

# 2) DB 마이그레이션 (drf 만 — Phase 1~4 + B 트랙 + token_blacklist 13개)
cd drf-server && python manage.py migrate

# 3) 검증
python -m pytest -q                             # drf  62 passed
cd ../fastapi-server && python -m pytest -q     # fast 22 passed

# 4) 양 서버 + Celery 재시작
```

### 주요 변경 (한 줄씩)

- **신규 앱 5개** — `dashboard` / `notices` / `operations` / `reference` / `training` (모델만 신설, 운영 진입 시 즉시 동작)
- **신규 모델 28개** — `BaseModel` / `AlertPolicy` / `Threshold` / `Menu` / `DataRetentionPolicy` 등 → 어드민에서 편집 가능
- **임계치 DB 일원화** — 가스/전력 임계치가 상수 → DB `Threshold` 모델 (facility 별 정책 가능)
- **알림 정책 시스템** — `AlertPolicy` + 9종 시드: Event 발생 시 자동 매칭 → Notification 생성
- **JWT 보안 강화 (옵트인)** — blacklist + ROTATE + access lifetime 1h (env 미설정 시 기존 동작)
- **WS 인증 (옵트인)** — `/ws/sensors/`, `/ws/worker/{id}/` JWT 검증
- **알람 파이프라인 정리** — `alarm-mapper.js` 추출 + `AlarmPopup` 그룹핑 + 서버 timestamp

### 신규 .env 변수 (모두 옵트인 — 빈 값이면 비활성)

| 변수 | drf | fastapi | 효과 |
|---|:---:|:---:|---|
| `INTERNAL_SERVICE_TOKEN` | ✅ | ✅ | drf ingest + fastapi alarm-push 양방향 토큰 |
| `JWT_SIGNING_KEY` | ✅ | ✅ | WS JWT 검증 (drf 의 `SIGNING_KEY` 와 동일 값) |
| `DRF_SERVICE_TOKEN` | — | ✅ | fastapi → drf 호출 시 헤더 부착 (= `INTERNAL_SERVICE_TOKEN`) |
| `JWT_ACCESS_TOKEN_LIFETIME_HOURS` | ✅ | — | 기본 24, 활성화 시 1~4 권장 |

> ⚠️ **양쪽 동일 값 필수**. 한쪽만 설정 시 모든 통신 차단. 활성화 절차는 §6.

### 작동 시 주의점 4가지

1. **마이그 비가역** — `token_blacklist` 13개 마이그. 운영 적용 시 백업 후 진행
2. **기존 refresh 토큰 재로그인 필요** — `ROTATE_REFRESH_TOKENS=True` 활성 시 기존 토큰 1회 사용 후 무효화. 사전 공지
3. **양 서버 + Celery 동시 재시작** — 토큰 옵트인 켤 때 한쪽만 재시작 시 통신 끊김
4. **WS access log token 노출 가능** — `?token=...` 쿼리 파라미터. 운영 시 access log filter 또는 WARN 레벨 권장

### 더 자세한 가이드

- 적용 절차 상세: [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) (Step 1~5 + 트러블슈팅)
- 옵트인 활성화 매트릭스 + 5분 절차: 본 문서 §6
- 변경 사유·설계 배경: [wave_1.md](wave_1.md) / [wave_2.md](wave_2.md) / [wave_3.md](wave_3.md) / [wave_4.md](wave_4.md)
- JS 권고 60건 적용 현황: 본 문서 §7

---

## 3. 5단계 흐름 — 왜 이 순서였는가

각 단계가 직전 단계의 변경을 검증·보강합니다.

### ① Phase 1~4 — 도메인 모델 대수술 (8 commits, 05-08)

| Phase | 한 일 |
|---|---|
| **Phase 1** | `operations`, `reference` 앱 신설 + `BaseModel` 통일 + `AlarmType` 10종 확장 |
| **Phase 2** | `HazardType`/`AlertPolicy`/`Notice`/`VR`/`Threshold`/`Menu` 6개 도메인 모델 신규 |
| **Phase 3** (3 PR) | `WorkerPosition.received_node` FK → `SafetyCheckSection` 3단계 마이그 → `SafetyCheckSession` UNIQUE 5단계 마이그 |
| **Phase 4** (3 PR) | 임계치/메뉴 DB 인프라 → `AlertPolicy` 매칭 + `Notification` 템플릿 → `DataRetentionPolicy` Celery 보관 배치 |

**왜 이 순서?** 4개 분석 plan(ISH/CJY/정휘훈)의 모델 변경을 거시 수렴. 기반(앱/베이스)→도메인(모델)→관계(FK/UNIQUE)→서비스(상수→DB) 의 의존성 그래프 그대로.

**다음 단계 트리거:** 30+건의 모델/시그니처가 바뀌었으니 기존 호출처가 깨졌는지 검증 필수.

### ② 회귀 점검 — Step 1~3 (4 commits, 05-08~09)

- **Step 1** (정적 분석): grep 기반으로 30+건 변경의 호출처 추적 → **즉시 깨짐 0건, 회귀 가능 1건** (`POWER_THRESHOLDS`)
- **Step 2** (fix): `POWER_THRESHOLDS` DB 일원화 (`Threshold.chart_max` 필드 추가) — 회귀 가능 1건 처치
- **Step 3** (테스트): 핵심 흐름 5개 / 27건 회귀 테스트 작성 + pytest 도입

**왜 이 순서?** 단위 테스트는 통과해도 grep 으로만 잡히는 호출처 깨짐은 별개. **변경 후 검증이 아니라 변경의 영향 범위를 먼저 정적 분석으로 입증** 후 fix → 회귀 테스트.

**다음 단계 트리거:** 운영 진입 직전, 잔여 운영 항목(시드/비동기/정책)을 병렬 처리할 차례.

### ③ B 운영 트랙 PR-A~H — 운영 안정화 (8 PR, 05-09)

| PR | 내용 |
|---|---|
| **PR-A** | fixture 시드 마이그 historical apps 패턴 통일 |
| **PR-B** | `BaseModel` 컨벤션 10개 모델 일괄 통일 |
| **PR-C** | 기본 시드 — `DataRetentionPolicy` 5종 + `AlertPolicy` 9종 |
| **PR-D** | `AppLog`/`IntegrationLog` Celery 비동기 INSERT |
| **PR-E** | `GasTypeChoices.LEL` dead code 제거 (센서 정의서 9종 일치) |
| **PR-F** | fastapi-server pytest 인프라 + 스모크 22건 |
| **PR-G** | Threshold facility별 정책 (`gas_facility_default` 그룹) |
| **PR-H** | e2e 알람 흐름 통합 테스트 4건 |

**왜 이 순서?** 8개 항목이 독립적이라 병렬 검증 효율화. PR-A(시드 패턴) → PR-B(BaseModel) 가 다음 PR 들의 표준 인프라 역할.

**다음 단계 트리거:** 코드리뷰 결과 critical 보안/정합 이슈 식별 → 운영 진입 직전 처리.

### ④ J 트랙 — 보안 + JS 정합 (B1~B12 + J1~J17, 05-10)

코드리뷰에서 식별된 critical 13건 + JS 정합 17건을 묶음 처리. 발표용 묶음으로는 Wave 1·2·3 으로 그룹핑.

| Wave | 내용 |
|---|---|
| **Wave 1** (정합·로깅) | `print()`→`logger`, `extra="ignore"`, `levelLabel`/`pad` 중복 제거, JS 로깅·layout 가드, JS 에러 핸들링 |
| **Wave 2** (JWT 보안) | SimpleJWT blacklist + ROTATE + access lifetime 1h, `LogoutView` refresh 블랙리스트, `Auth._refresh` 싱글톤 |
| **Wave 3** (WS 인증) | fastapi JWT 검증 인프라 + drf `SIGNING_KEY` 명시, `/ws/sensors/`·`/ws/worker/{id}/` 인증, `ws-client` `attachToken` 일관 적용 (8곳) |

**왜 이 순서?** 보안은 운영 진입 직전이 마지막 안전망. 정합·로깅(Wave 1) → 토큰 정책(Wave 2) → 채널 인증(Wave 3) 의 의존 순서.

**다음 단계 트리거:** 모든 코드 변경 종료. 다음 팀원·머지자가 따라올 수 있도록 문서 정리.

### ⑤ 문서화 (5 commits, 05-10)

- Phase 1~4 + 회귀 의사결정 통합 ([docs/phases/team_decisions_summary.md](docs/phases/team_decisions_summary.md))
- B 트랙 종합 overview ([docs/phases/post_phase4_b_track_overview.md](docs/phases/post_phase4_b_track_overview.md))
- 도메인별 코드리뷰 11종 ([docs/codereviews/2026_05_09/](docs/codereviews/2026_05_09/))
- JS 핵심 공유 계층 함수 단위 분석 7종 ([docs/refactor/js/2026_05_09/](docs/refactor/js/2026_05_09/)) — **분석·권고 문서** (60건 권고, 적용 현황은 §7 참조)
- Wave 1~3 실행 보고서 ([docs/refactor/waves/2026_05_09/](docs/refactor/waves/2026_05_09/))
- 적용 가이드 ([docs/refactor/waves/2026_05_09/MIGRATION_GUIDE.md](docs/refactor/waves/2026_05_09/MIGRATION_GUIDE.md))

---

## 4. 역할별 읽을 문서

### L1 — 머지 전 모두 (5분, 4 문서)

| 문서 | 한 줄 |
|---|---|
| [CHANGES_REVIEW.md](docs/refactor/waves/2026_05_09/CHANGES_REVIEW.md) | **🌟 종합 변경 인벤토리** (47 commits / 5 카테고리 / 리뷰어 체크리스트) |
| [MIGRATION_GUIDE.md](docs/refactor/waves/2026_05_09/MIGRATION_GUIDE.md) | 머지·적용 5단계 (의존성/DB/env) |
| [post_phase4_b_track_overview.md](docs/phases/post_phase4_b_track_overview.md) | Phase 1~4 + 회귀 + B 트랙 한 페이지 |
| [team_decisions_summary.md](docs/phases/team_decisions_summary.md) | 33+건 의사결정 옵션·채택·근거 |
| [00_pr_verification_checklist.md](docs/changelog/00_pr_verification_checklist.md) | PR 검증 체크리스트 |

### L2 — 본인 영역 코드 반영 시 (해당 영역만)

| 영역 | 문서 |
|---|---|
| **백엔드 모델** | [phase_1_report.md](docs/phases/phase_1_report.md) · [phase_2_report.md](docs/phases/phase_2_report.md) · [phase_3_pr1~3_report.md](docs/phases/) · [phase_4_pr1~3_report.md](docs/phases/) · [post_phase4_step1~3_report.md](docs/phases/) |
| **운영/시드/정책** | [post_phase4_b_track_pr_a~h_report.md](docs/phases/) (PR-A~H 8건) |
| **인증/JWT 보안** | [wave_2.md](docs/refactor/waves/2026_05_09/wave_2.md) |
| **WebSocket** | [wave_3.md](docs/refactor/waves/2026_05_09/wave_3.md) · [09_realtime_websocket.md](docs/codereviews/2026_05_09/09_realtime_websocket.md) |
| **프론트(JS)** | [00_overview.md](docs/refactor/js/2026_05_09/00_overview.md) + 담당 그룹 (01_auth_session ~ 06_utils_config) |
| **보안 점검** | [99_security_summary.md](docs/codereviews/2026_05_09/99_security_summary.md) |

### L3 — 깊이 이해용 (선택)

- Phase plan 4종 ([phase_1_plan.md](docs/phases/phase_1_plan.md) · [phase_2_plan.md](docs/phases/phase_2_plan.md) · [phase_3_plan.md](docs/phases/phase_3_plan.md) · [phase_4_plan.md](docs/phases/phase_4_plan.md)) — 의사결정 논의 재현
- 코드리뷰 도메인별 ([01_auth_access](docs/codereviews/2026_05_09/01_auth_access.md) ~ [09_realtime_websocket](docs/codereviews/2026_05_09/09_realtime_websocket.md)) — 각 240줄 내외

---

## 5. 머지/적용 체크리스트 (요약)

상세는 [MIGRATION_GUIDE.md](docs/refactor/waves/2026_05_09/MIGRATION_GUIDE.md) 참조.

1. **의존성 갱신** — `requirements.txt` / `requirements-dev.txt` (drf-server, fastapi-server 양쪽)
2. **DB 마이그레이션** — `python manage.py migrate` (Phase 1~4 + B 트랙 PR-A~G 의 마이그가 누적)
3. **시드 적용** — 마이그에 포함된 `update_or_create` 시드 자동 실행 (수동 loaddata 불필요)
4. **env 변수** — `SIGNING_KEY` (drf), `JWT_SIGNING_KEY` / 서비스 토큰 (fastapi), Celery broker 확인
5. **검증** — `pytest` (drf 62건 + fastapi 22건 + e2e 4건 = 88건 모두 green)

---

## 6. Phase 5 옵트인 활성화 — "보안 켜는 법"

> Phase 5(서비스 토큰 + WS JWT) 코드는 머지되어 있지만, **환경변수가 비어 있으면 무인증으로 동작**합니다. 운영 환경에 보안을 실제로 적용하려면 아래 절차가 필요합니다.

### 6.1 활성화 매트릭스 — 지금 상태 진단

[drf-server/.env](drf-server/.env) 와 [fastapi-server/.env](fastapi-server/.env) 의 두 변수를 확인:

| `INTERNAL_SERVICE_TOKEN` | `JWT_SIGNING_KEY` | drf ingest | alarm-push | WS 인증 | 상태 |
|:---:|:---:|:---:|:---:|:---:|---|
| 빈 값 | 빈 값 | ❌ | ❌ | ❌ | **기존 동작** (회귀 0, 보안 효과 0) |
| 설정 | 빈 값 | ✅ | ✅ | ❌ | drf ingest만 보호 |
| 빈 값 | 설정 | ❌ | ❌ | ✅ | WS만 보호 |
| 설정 | 설정 | ✅ | ✅ | ✅ | **완전 활성화 (권장)** |

> ⚠️ **양 서비스 동일 값 필수**. 한쪽만 설정하면 모든 통신 차단됨.

### 6.2 5분 활성화 절차

상세는 [MIGRATION_GUIDE.md §3 Step 3~5](docs/refactor/waves/2026_05_09/MIGRATION_GUIDE.md) 참조. 요약:

```bash
# 1) 토큰 2개 생성
python -c "import secrets; print(secrets.token_urlsafe(32))"  # → INTERNAL_SERVICE_TOKEN
python -c "import secrets; print(secrets.token_urlsafe(32))"  # → JWT_SIGNING_KEY

# 2) drf-server/.env 와 fastapi-server/.env 양쪽에 동일 값으로 추가
INTERNAL_SERVICE_TOKEN=<첫 번째 값>
JWT_SIGNING_KEY=<두 번째 값>

# 3) 양 서버 + Celery 동시 재시작 (한쪽만 켜면 통신 끊김)
sudo systemctl restart drf-server fastapi-server celery-worker

# 4) 검증
cd drf-server && .venv/bin/python -m pytest -q       # 62 passed
cd fastapi-server && .venv/bin/python -m pytest -q   # 22 passed
# 브라우저: 로그인 → 대시보드 → WS 연결 / wscat 토큰 없이 → close 1008 확인
```

### 6.3 활성화 후 변하는 것 (사용자/IoT 영향)

| 영향 | 활성화 전 | 활성화 후 |
|---|---|---|
| 로그인 access 만료 | 24h | **1h** (자동 refresh) |
| 로그아웃 | 클라이언트 정리 | **서버 측 refresh 무효화** |
| WS 연결 | 누구나 | **JWT 검증된 사용자만** |
| `/api/monitoring/gas/` (drf) | 무인증 | **Bearer 토큰 필수** |
| `/api/sensors/gas` (fastapi 입구) | 무인증 | **변경 없음** (펌웨어 협업 별도 sprint) |

> ⚠️ **기존 발급된 refresh 토큰**은 자동 무효화 안 됨. 운영 적용 시 사용자 재로그인 안내 필요.

### 6.4 단계적 활성화 (권장)


1. 먼저 `INTERNAL_SERVICE_TOKEN` 만 설정 → drf ingest 보호 → 며칠 안정화
2. 이후 `JWT_SIGNING_KEY` 추가 → WS 보호까지 완전 활성화

자세한 운영 주의사항(롤링 배포·refresh 토큰 재발급·access log 토큰 노출): [MIGRATION_GUIDE.md §6](docs/refactor/waves/2026_05_09/MIGRATION_GUIDE.md)

---

## 7. JS 리팩토링 권고 60건 — 적용 vs 후속 sprint

`docs/refactor/js/2026_05_09/` 는 6개 기능 그룹 × 약 10건 = **총 60건의 리팩토링 권고**를 담은 분석 문서입니다 (적용 보고서 아님). **이 브랜치에 24건 적용** (J 트랙 17 + 추가 7), 나머지 ~36건은 후속 sprint 대상.

### 7.1 적용된 24건

**J 트랙 (J1~J17, 17건)** — Wave 1·2·3 으로 그룹핑되어 적용.

**추가 7건 (2026-05-10 작업)** — 미적용 [상] 권고 중 팀 내부 결정으로 적용 가능한 것:

| 권고 | 변경 위치 | 효과 |
|---|---|---|
| **02 R1** WS 지수 백오프 + 최대 시도 | [ws-client.js](drf-server/static/js/shared/ws-client.js) | 서버 영구 다운 시 자원 폭주 방지 (1s → 30s 상한, ±30% 지터, 20회 후 포기) |
| **03 R1** alarm-mapper.js 추출 | 신규 [alarm-mapper.js](drf-server/static/js/shared/alarm-mapper.js) + 3 callers + 4 템플릿 | 백엔드 키 매핑 단일화 (3곳 → 1곳) |
| **04 R1** Menu.render createElement 패턴 | [layout.js](drf-server/static/js/shared/layout.js) Menu.render | XSS 자동 방지 (`textContent` 처리) |
| **05 R2** loadMySafetyStatus → Auth.apiFetch | [dashboard/app.js](drf-server/static/js/dashboard/app.js) | 인증 일관·자동 refresh·401 redirect (J10 완성) |
| **03 R3** 서버 timestamp (created_at) | [tasks.py](drf-server/apps/alerts/tasks.py) `_push_to_ws()` + [AlarmPayload](fastapi-server/internal/routers/alarm_router.py) + [alarm-mapper.js](drf-server/static/js/shared/alarm-mapper.js) | 알람 발신 시각 정확도 (도착 시각 → 생성 시각) |
| **05 R3** `caution/safe` ↔ `warning/normal` 변환층 단일화 | 신규 [level-mapper.js](drf-server/static/js/shared/level-mapper.js) + [dashboard/websocket.js](drf-server/static/js/dashboard/websocket.js) `_riskClass`/`_riskLabel` 제거 | 옵션 B (CSS 리네임 옵션 A는 10+ 파일 영향이라 후속 sprint 보류) |
| **03 R2** AlarmPopup 큐 정책 (옵션 B+A) | [alarm-popup.js](drf-server/static/js/shared/alarm-popup.js) | 같은 센서·동일 레벨 5초 내 그룹핑 (`×N` 표시) + 큐 풀 시 `droppedCount` 콘솔 노출 |

**검증:** drf 62 + fastapi 22 = 84 tests green. Node 문법 검사 모든 신규/수정 JS 파일 OK.

### 7.2 미적용 — 별도 PR (~3건 [상])

| 권고 | 미적용 이유 | 처리 방안 |
|---|---|---|
| **02 R3** WS 메시지 catch-up (last_event_id) | **서버 측 ring buffer 설계 필요** — 메모리 상한, 재시작 시 buffer 손실 정책, 클라이언트 last_event_id 검증 race 등 별도 검토 항목 다수 | fastapi `state.py`/`broadcast.py` + WS 핸들러 별도 PR (운영 진입 후 가능) |
| **05 R3 (옵션 A)** CSS 클래스 리네임 (`caution`→`warning`, `safe`→`normal`) | 옵션 B(매퍼) 적용으로 **변환층은 단일화 완료**. CSS 리네임은 10+ 파일 영향이라 sprint 단위 작업 | 후속 sprint — `caution-text`, `safe-text` 등 누락 없이 일괄 |
| **04 R2** initHeaderAndSNB getMe 실패 처리 | 인증 만료 vs 네트워크 실패 구분 UX 정책 필요 | 화면 동작 확정 후 적용 |

### 7.3 미적용 — [중] / [하] 우선순위 (~33건)

기능 그룹별 `R*` 항목 중 미적용은 [01_auth_session.md](docs/refactor/js/2026_05_09/01_auth_session.md) ~ [06_utils_config.md](docs/refactor/js/2026_05_09/06_utils_config.md) 본문에서 우선순위 [중/하] 표시 항목들이 해당. **운영 진입에 시급하지 않으니 다음 sprint 정리 시 한 번에 검토 권장.**

대표 [중] 항목: `01 R4` 비밀번호 검증 정책 중앙화, `02 R5` WS heartbeat/ping, `03 R5` EventBus 패턴, `04 R3` SVG 아이콘 sprite 분리, `06 R8` AppConfig 환경별 분기 명시.

### 7.4 권고 vs 적용 매트릭스 (도메인 횡단 Top 10 기준)

| # | 권고 (00_overview.md Top 10) | 적용? | 처리 |
|---|---|:---:|---|
| 1 | AlarmPopup 큐 silent drop 재설계 | ✅ | **이번 작업** (옵션 B 그룹핑 + 옵션 A drop 카운트) |
| 2 | alarm-mapper.js 추출 | ✅ | **이번 작업** |
| 3 | Auth._refresh 동시성 가드 | ✅ | J12 |
| 4 | levelLabel dead code 제거 | ✅ | J1 |
| 5 | WS 메시지 catch-up | ❌ | 7.2 (서버 ring buffer 설계 별도 PR) |
| 6 | WS 지수 백오프 + 최대 시도 | ✅ | **이번 작업** |
| 7 | Menu.render createElement | ✅ | **이번 작업** |
| 8 | initApp `.catch()` | ✅ | J9 |
| 9 | loadMySafetyStatus Auth.apiFetch | ✅ | **이번 작업** (J10 완성) |
| 10 | `caution/safe` ↔ `warning/normal` contract | ✅ | **이번 작업** (옵션 B 변환층 단일화 — CSS 리네임 옵션 A는 후속 sprint) |

→ **Top 10 중 9건 적용 (이전 4건 + 이번 작업 5건)**, 1건만 미적용 (02 R3 — 서버 ring buffer 설계 PR).

---

## 8. FAQ — "이거 왜 했어요?"

**Q. 왜 PR 을 8개 (B 트랙) + 17개 (J 트랙) 로 잘게 쪼갰나요?**
운영 항목·정합 항목이 서로 독립적이라 묶어 머지하면 충돌 시 디버깅 비용이 폭증. 작은 단위로 쪼개면 각 PR 의 검증 범위가 좁아져 리뷰·롤백이 쉬움.

**Q. 회귀 점검을 따로 한 이유?**
단위 테스트가 통과해도 **grep 으로만 잡히는 호출처 깨짐**은 별개. 30+건 모델 변경 후 정적 분석으로 영향 범위를 먼저 입증한 다음 fix·테스트 보강.

**Q. `POWER_THRESHOLDS` 한 건만 fix 한 이유?**
Step 1 정적 분석 결과 즉시 깨짐 0, 회귀 가능 1건. 1건만 처치하고 그 외에는 회귀 테스트로 보강.

**Q. B 트랙 / J 트랙 / Wave 명칭이 섞여 있는데?**
- **B**=백엔드 운영 (B1~B12) · **J**=JavaScript (J1~J17) · **PR-A~H**=B 운영 트랙 8 PR
- **Wave 1~3** = J 트랙(+ 일부 B 트랙)을 발표·적용용으로 3단계 그룹핑
- → 같은 작업의 **다른 분류 축**. 코드 측엔 B/J 번호, 문서 측엔 Wave 가 보입니다.

**Q. Phase 5 는 어디 갔어요? 못 찾겠는데요.**
**별도 브랜치가 아니라 이 브랜치 안에 있는 "옵트인 보안 인증" 코드네임**입니다. `phase_5_plan.md` / `phase_5_report.md` 단독 문서가 없어서 안 보일 뿐 코드는 들어있습니다 (커밋 `00ae07c` + Wave 2/3 의 일부).
- **포함 작업:** ingest endpoint 토큰 + drf Celery → fastapi alarm-push 양방향 토큰 + LogoutView refresh 블랙리스트 + WS JWT 인증
- **켜는 법:** **§6 Phase 5 옵트인 활성화** 참조 (이 문서 위쪽). 환경변수 미설정 시 기존 무인증 동작 그대로 (회귀 위험 0).
- **읽을 곳:** [wave_1.md §B3+B4](docs/refactor/waves/2026_05_09/wave_1.md) (line 161~) · [wave_2.md](docs/refactor/waves/2026_05_09/wave_2.md) · [wave_3.md](docs/refactor/waves/2026_05_09/wave_3.md) · [99_security_summary.md](docs/codereviews/2026_05_09/99_security_summary.md)

**Q. 신규 시드(AlertPolicy 9종, DataRetention 5종, gas_facility_default) 는 어디서 정의?**
PR-C ([post_phase4_b_track_pr_c_report.md](docs/phases/post_phase4_b_track_pr_c_report.md)) 와 PR-G ([post_phase4_b_track_pr_g_report.md](docs/phases/post_phase4_b_track_pr_g_report.md)) 에 정의 + 마이그에 자동 시드.

**Q. 센서 정의서와 안 맞는 항목은?**
PR-E 에서 `GasTypeChoices.LEL` 1건 제거. 센서 정의서 9종과 100% 일치 ([post_phase4_b_track_pr_e_report.md](docs/phases/post_phase4_b_track_pr_e_report.md)).

---

## 9. 참고 — 전체 문서 폴더 구조

```
docs/
├── changelog/
│   └── 00_pr_verification_checklist.md         (수정)
├── codereviews/2026_05_09/                     (신규 11개)
│   ├── 00_overview.md
│   ├── 01_auth_access.md ~ 09_realtime_websocket.md
│   └── 99_security_summary.md
├── phases/                                     (신규 23개)
│   ├── phase_1~4_plan.md (4)
│   ├── phase_1~4_pr*_report.md (12)
│   ├── post_phase4_regression_plan.md
│   ├── post_phase4_step1~3_report.md (3)
│   ├── post_phase4_b_track_overview.md
│   ├── post_phase4_b_track_impact_analysis.md
│   ├── post_phase4_b_track_pr_a~h_report.md (8)
│   └── team_decisions_summary.md
└── refactor/
    ├── js/2026_05_09/                          (신규 7개, JS 함수 단위 분석)
    └── waves/2026_05_09/                       (신규 4개)
        ├── MIGRATION_GUIDE.md
        ├── TEAM_BRIEF.md                       ← 이 문서
        └── wave_1~3.md (3)
```

---

**문의:** 이 브리프를 읽고도 막히는 부분이 있으면 해당 단계의 plan/report 문서 번호를 알려주세요. 문서가 부족하면 보강하고, 문서가 답하는데 못 찾으셨으면 이 브리프를 갱신합니다.
