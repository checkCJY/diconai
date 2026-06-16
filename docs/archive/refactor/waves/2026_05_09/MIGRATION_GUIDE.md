# 적용 가이드 — `feature/0508_refactory_code` 브랜치

> **대상**: 이 브랜치를 main/develop으로 머지하려는 팀원, 또는 브랜치를 체크아웃해 작업하려는 팀원
> **요약**: Wave 1~3 리팩토링 (보안·정합·로깅) + 분석 산출물. **17개 commit, 변경 코드 ~520줄**.
> **핵심**: 모든 보안 변경이 **옵트인 패턴** — env 미설정 시 기존 동작 유지 (회귀 위험 0).

---

## 0. 한 페이지 요약

이 브랜치를 받아서 적용하면:

| 단계 | 작업 | 시간 |
|---|---|---|
| 1 | `git pull` 후 의존성 설치 (`uv pip install -r fastapi-server/requirements.txt`) | 1분 |
| 2 | DB 마이그레이션 실행 (`python manage.py migrate token_blacklist`) | 1분 |
| 3 | (옵션) env 설정해 보안 활성화 | 5분 |
| 4 | 양 서버 재시작 | 1분 |
| 5 | 회귀 검증 (`pytest`, 브라우저) | 10분 |

**env 설정 안 해도 동작**: 기존 동작 그대로. 단, **보안 강화 효과는 0**.
**env 설정 시**: WS 인증, ingest 토큰 검증, JWT blacklist 모두 활성화.

---

## 1. 17개 commit 한 줄 요약

시간 순 (오래된 → 최신):

| # | Commit | 한 줄 요약 |
|---|---|---|
| 1 | `7e6b404` refactor : **B5** | `WorkerSummaryView`에 `IsSuperAdminOrFacilityAdmin` 권한 클래스 적용 (이전 view body raise 제거) |
| 2 | `b6cb6ce` refactor : **B1** | positioning view의 `print()` → `logger.exception` (CLAUDE.md 컨벤션 준수) |
| 3 | `0770423` refactor : **B2** | `AlarmPayload.model_config["extra"]` `"allow"` → `"ignore"` (미정의 필드 silent drop) |
| 4 | `00ae07c` feat&nbsp;&nbsp;&nbsp; : **B3+B4** | **신규** `apps/core/authentication.py::ServiceTokenAuthentication` + ingest 4개 view + Celery alarm-push에 토큰 헤더 (옵트인) |
| 5 | `eb60cfc` refactor : **J1-J4** | JS 정합: `levelLabel` dead code 제거 / `pushData` 검증 / `WS_BASE` 운영 가드 / `safety_history.js` pad 로컬 재정의 제거 |
| 6 | `0b67e7c` refactor : **J5-J8** | ws-client·layout 로깅: AppConfig·Auth 부재 console.warn / iconMap 미정의 warn / `ROLE_LABEL` 모듈 상수화 / `handleRefresh` setTimeout 누적 방지 |
| 7 | `5ee7628` refactor : **J9-J11** | 에러 핸들링: `initApp().catch()` / `loadMySafetyStatus` console.warn / `Auth.getMe` console.warn |
| 8 | `4735670` feat&nbsp;&nbsp;&nbsp; : **B6-B8** | SimpleJWT `token_blacklist` 앱 추가 + `ROTATE_REFRESH_TOKENS=True` + `BLACKLIST_AFTER_ROTATION=True` + `ACCESS_TOKEN_LIFETIME` 24h → 1h |
| 9 | `3567c60` feat&nbsp;&nbsp;&nbsp; : **B9** | `LogoutView`가 body의 `refresh` 토큰을 `RefreshToken().blacklist()` 등록 |
| 10 | `c58373d` refactor : **J12+J13** | `Auth._refresh` 싱글톤 in-flight Promise 가드 (다중 401 race 차단) + Logout 호출 시 refresh body 동봉 |
| 11 | `39d2ba7` feat&nbsp;&nbsp;&nbsp; : **B11** | fastapi에 `PyJWT==2.10.1` 추가 + **신규** `fastapi-server/websocket/auth.py` + `JWT_SIGNING_KEY`/`JWT_ALGORITHM` env + drf `SIMPLE_JWT["SIGNING_KEY"]` 명시 |
| 12 | `947cbc8` feat&nbsp;&nbsp;&nbsp; : **B12** | `/ws/sensors/`, `/ws/worker/{user_id}/` 엔드포인트에 JWT 검증 (옵트인) + worker는 path user_id 일치 검증 |
| 13 | `f8edd2d` refactor : **J17** | 8개 WS 호출자 모두 `WSClient.connect(path, { attachToken: true })` 일괄 적용 |
| 14 | `ac900db` docs&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; | `docs/codereviews/2026_05_09/` 11종 — 도메인별 코드리뷰 보고서 |
| 15 | `518f67b` docs&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; | `docs/refactor/js/2026_05_09/` 7종 — JS 핵심 공유 계층 함수 분석 |
| 16 | `a7b7dec` docs&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; | `docs/refactor/waves/2026_05_09/` 3종 — Wave 1~3 실행 보고서 |
| 17 | `1ebf945` docs&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; | `docs/phases/team_decisions_summary.md` — Phase 1~4 의사결정 통합 정리 |

**분류 요약**:
- 코드 변경 13개 (B 9개 + J 4개 묶음)
- docs 4개 (분석·정리)

---

## 2. 변경 인벤토리

### 2.1 신규 파일 (2개)
```
drf-server/apps/core/authentication.py        ← ServiceTokenAuthentication (B3+B4)
fastapi-server/websocket/auth.py              ← verify_jwt_from_ws_query (B11)
```

### 2.2 수정 파일 (코드, 16개)
**백엔드 drf** (8):
```
config/settings.py                            ← INSTALLED_APPS, SIMPLE_JWT, env 추가
apps/accounts/views/auth_views.py             ← LogoutView blacklist
apps/alerts/tasks.py                          ← Celery alarm-push 토큰 헤더
apps/alerts/views/alarm_record.py             ← WorkerSummaryView 권한
apps/monitoring/views/gas_data.py             ← ServiceTokenAuthentication 적용
apps/monitoring/views/power_data.py           ← 동
apps/positioning/views/position_views.py      ← 동 + logger.exception
```

**백엔드 fastapi** (3):
```
core/config.py                                ← INTERNAL_SERVICE_TOKEN, JWT_SIGNING_KEY, JWT_ALGORITHM
internal/routers/alarm_router.py              ← extra="ignore" + 토큰 검증
websocket/routers/ws_router.py                ← /ws/sensors/, /ws/worker/{id}/ 인증
requirements.txt                              ← PyJWT==2.10.1
```

**JS** (8):
```
shared/auth.js                                ← _refresh 싱글톤, getMe console.warn
shared/config.js                              ← WS_BASE 운영 가드
shared/ws-client.js                           ← _resolveUrl console.warn 3종
shared/layout.js                              ← ROLE_LABEL 상수, iconMap warn, handleRefresh, logout body
shared/util.js                                ← levelLabel 제거, pushData 검증
shared/app-sub.js                             ← initApp().catch()
dashboard/app.js                              ← initApp().catch(), loadMySafetyStatus warn
detail/safety_history.js                      ← pad 로컬 재정의 제거
+ 7개 WS 호출자 (J17): alarm-ws, worker-ws, dashboard/websocket, detail/websocket_*, monitoring_workers
```

### 2.3 신규 docs (22 파일)
```
docs/codereviews/2026_05_09/                  ← 11 파일 (도메인별 리뷰)
docs/refactor/js/2026_05_09/                  ← 7 파일 (JS 함수 분석)
docs/refactor/waves/2026_05_09/               ← 3 파일 (Wave 보고서) + 본 문서
docs/phases/team_decisions_summary.md         ← Phase 1~4 결정 정리
```

### 2.4 의존성 추가 (1개)
- `PyJWT==2.10.1` (fastapi-server)

### 2.5 DB 마이그레이션 (1세트)
- `token_blacklist` 앱 13개 마이그레이션 (django의 `simplejwt` 표준)

### 2.6 환경 변수 추가/변경 (5개)

**drf-server (.env)**:
| Env | 기본값 | 변경 내용 | 필수? |
|---|---|---|---|
| `INTERNAL_SERVICE_TOKEN` | `""` (빈 값) | **신규** — 빈 값이면 인증 비활성 | ⚠️ 옵트인 활성화 권장 |
| `JWT_SIGNING_KEY` | `SECRET_KEY` (default) | **신규** — fastapi와 동일 값 | ⚠️ 옵트인 활성화 권장 |
| `JWT_ACCESS_TOKEN_LIFETIME_HOURS` | `24` → **`1`** | **default 변경** — 운영 정책에 따라 조정 가능 | 자동 적용 |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | `30` (변경 없음) | (기존) | 자동 적용 |

**fastapi-server (.env)**:
| Env | 기본값 | 변경 내용 | 필수? |
|---|---|---|---|
| `INTERNAL_SERVICE_TOKEN` | `""` | **신규** — drf와 동일 값 | ⚠️ drf와 동기화 필수 |
| `JWT_SIGNING_KEY` | `""` | **신규** — drf와 동일 값 | ⚠️ drf와 동기화 필수 |
| `JWT_ALGORITHM` | `"HS256"` | **신규** — 기본값 그대로 둠 | 자동 적용 |

### 2.7 명령어/실행 절차 변경
- **명령어 변경 없음** — `runserver`, `uvicorn`, `celery` 등 그대로
- **마이그레이션 추가**: `python manage.py migrate token_blacklist` (1회)
- **의존성 재설치**: `uv pip install -r fastapi-server/requirements.txt` (PyJWT 추가)

---

## 3. 적용 절차 (Step-by-Step)

### Step 1. 브랜치 체크아웃 + 의존성

```bash
cd /home/cjy/diconai
git fetch origin
git checkout feature/0508_refactory_code

# fastapi-server PyJWT 설치
cd fastapi-server
VIRTUAL_ENV=$PWD/.venv uv pip install -r requirements.txt
# 또는: source .venv/bin/activate && pip install -r requirements.txt

# drf-server는 의존성 변경 없음 — 패스
```

### Step 2. DB 마이그레이션

```bash
cd /home/cjy/diconai/drf-server
.venv/bin/python manage.py migrate token_blacklist
# Applying token_blacklist.0001_initial... OK
# ... (13개 적용)
```

> ⚠️ **기존 발급된 refresh 토큰**은 자동 무효화 안 됨. 운영 적용 시 사용자 재로그인이 필요할 수 있음 (사전 공지 권장).

### Step 3. (옵션) env 활성화 — 보안 강화 적용

이 단계를 건너뛰면 **Wave 1~3 보안 효과가 0** (코드만 머지된 상태).

**a) 동일 토큰 생성 (양 서비스 공유)**:
```bash
# 32자 이상 랜덤 토큰 2개 생성
python -c "import secrets; print(secrets.token_urlsafe(32))"  # INTERNAL_SERVICE_TOKEN
python -c "import secrets; print(secrets.token_urlsafe(32))"  # JWT_SIGNING_KEY
```

**b) drf-server/.env 추가**:
```bash
INTERNAL_SERVICE_TOKEN=<위에서 생성한 첫 번째 값>
JWT_SIGNING_KEY=<위에서 생성한 두 번째 값>
# 운영 정책에 따라 조정:
JWT_ACCESS_TOKEN_LIFETIME_HOURS=1   # 1h가 무리면 2~4h로 조정 가능
```

**c) fastapi-server/.env 추가/수정**:
```bash
INTERNAL_SERVICE_TOKEN=<drf와 동일 값>
JWT_SIGNING_KEY=<drf와 동일 값>
# JWT_ALGORITHM은 기본 HS256, 변경 불필요

# ⚠️ 기존 DRF_SERVICE_TOKEN(빈 문자열)도 같은 값으로 채워야 함.
# fastapi → drf 호출(가스/전력 ingest)에서 Authorization 헤더로 부착되는 값으로,
# 비워두면 옵트인 켠 drf가 401 반환 → 알람/모니터링 흐름 끊김.
DRF_SERVICE_TOKEN=<drf의 INTERNAL_SERVICE_TOKEN과 동일 값>
```

> ⚠️ **양 서비스 동일 값 필수**. 한쪽만 설정 시 인증 실패 → 모든 통신 차단.
>
> ⚠️ **fastapi 측 토큰 변수 2개 모두 채울 것** (`INTERNAL_SERVICE_TOKEN` = 인입 검증용 / `DRF_SERVICE_TOKEN` = drf로 나갈 때 헤더 부착용). 단일 토큰 운영이면 둘 다 같은 값.

### Step 4. 양 서버 재시작 (env 변경 반영)

> 양쪽 동시 재시작 권장 (옵트인 활성화는 양쪽 동시에 켜져야 함).
> Celery는 drf-server의 venv를 사용 (`apps/alerts/tasks.py`에서 토큰 헤더 사용).

#### 4-A. 로컬 개발 (uv)

각 서버 venv가 분리돼 있으므로 **터미널 3개**에서 각각 실행:

```bash
# 터미널 1: drf-server
cd drf-server
source .venv/bin/activate
python manage.py runserver 0.0.0.0:8000

# 터미널 2: fastapi-server
cd fastapi-server
source .venv/bin/activate
uvicorn app:app --reload --port 8001

# 터미널 3: celery (drf-server venv)
cd drf-server
source .venv/bin/activate
celery -A config worker -l info
```

또는 `uv run`으로 activate 생략:

```bash
cd drf-server     && uv run manage.py runserver 0.0.0.0:8000
cd fastapi-server && uv run uvicorn app:app --reload --port 8001
cd drf-server     && uv run celery -A config worker -l info
```

#### 4-B. 운영 (systemd 등 프로세스 매니저)

```bash
sudo systemctl restart drf-server
sudo systemctl restart fastapi-server
sudo systemctl restart celery-worker
```

> 서비스 유닛명은 환경에 따라 다를 수 있음. supervisor/pm2 등을 쓰는 경우 해당 매니저의 restart 명령으로 대체.

### Step 5. 회귀 검증

```bash
# 자동 테스트
cd drf-server && .venv/bin/python -m pytest -q       # 62 passed
cd fastapi-server && .venv/bin/python -m pytest -q   # 22 passed

# 브라우저 수동
# 1) 로그인 → /dashboard/ 접근
# 2) 서브페이지 진입 (모니터링·안전·이벤트)
# 3) admin 페이지 진입 (관리자만)
# 4) 로그아웃 → 재로그인
# 5) WS 연결: 콘솔에서 dashboard/websocket 정상 작동 확인
# 6) (옵트인 활성 시) 토큰 없이 wscat으로 WS 연결 → close 1008 확인
```

---

## 4. 옵트인 활성화 매트릭스

| env 상태 | drf ingest 인증 | fastapi alarm-push 인증 | WS 인증 | 효과 |
|---|---|---|---|---|
| 양쪽 모두 미설정 | ❌ 무인증 | ❌ localhost만 | ❌ 비활성 | **기존 동작** (회귀 0) |
| `INTERNAL_SERVICE_TOKEN` 설정 | ✅ 토큰 검증 | ✅ 토큰 검증 | ❌ 비활성 | drf ingest 보호 |
| `JWT_SIGNING_KEY` 설정 | ❌ | ❌ | ✅ 토큰 검증 | WS 보호 |
| 둘 다 설정 | ✅ | ✅ | ✅ | **완전 활성화 (권장)** |

> 💡 단계적 활성화 가능: `INTERNAL_SERVICE_TOKEN`만 먼저 → 안정화 → `JWT_SIGNING_KEY` 추가.

---

## 5. 새 동작 — 활성화 후 변경되는 것

### 5.1 사용자 측면 (브라우저)

| 동작 | 활성화 전 | 활성화 후 |
|---|---|---|
| 로그인 후 access 만료 | 24시간 후 | **1시간 후** (자동 refresh로 사용자 인지 X) |
| 로그아웃 | 클라이언트 토큰만 정리 | **서버 측 refresh 즉시 무효화** |
| 다중 디바이스 로그아웃 | 다른 디바이스 영향 0 | (선택) 비번 변경 시 강제 로그아웃 가능 (B10 별도) |
| WS 연결 | 누구나 가능 | **JWT 검증된 사용자만** |

### 5.2 IoT 장비 측면

| 엔드포인트 | 활성화 전 | 활성화 후 |
|---|---|---|
| `/api/sensors/gas` (fastapi) | 무인증 | (변경 없음) |
| `/api/monitoring/gas/` (drf, fastapi가 호출) | 무인증 | **`Authorization: Bearer <INTERNAL_SERVICE_TOKEN>` 필수** |
| `/api/positioning/receive/` (drf) | 무인증 | **토큰 필수** |
| `/ws/position/` (IoT 위치 WS) | (변경 없음) | (변경 없음) — IoT 펌웨어 협업 별도 sprint |

> ⚠️ fastapi가 자체 호출은 이미 `DRF_SERVICE_TOKEN` 헤더를 보내므로 자동 호환. **외부에서 직접 drf로 호출하는 곳이 있다면** 토큰 추가 필요.

### 5.3 운영 모니터링

- 새 console.warn/error 메시지 다수 추가됨 (정상 시는 출력 0)
- 의심 시그널: `[Auth._refresh]`, `[WSClient]`, `[Menu] icon not defined`, `[ws-auth]`
- WS access log에 `?token=...` 노출 가능 → **운영 시 access log filter 또는 WARN 레벨 권장**

---

## 6. 주요 주의사항

### 6.1 회귀 위험 0 (옵트인 비활성 시)
- 모든 보안 변경은 옵트인. env 미설정이면 기존 동작 그대로
- pytest 84/84 통과 (drf 62 + fastapi 22)
- ruff lint+format 통과

### 6.2 활성화 시 주의
1. **양 서비스 env 동시 갱신 필수**: 한쪽만 설정 시 통신 즉시 차단. 롤링 배포 시 잠시 양쪽 비활성 → 동시 재시작 → 양쪽 활성화 권장.
2. **마이그레이션 비가역**: `token_blacklist` 13개 마이그레이션. 운영 적용 시 백업 후 진행.
3. **기존 토큰 사용자 재로그인 필요**: refresh 회전이 활성화되면 기존 발급 refresh가 한 번 사용 후 무효화. 사전 공지.
4. **`JWT_ACCESS_TOKEN_LIFETIME_HOURS=1`이 운영에 무리이면**: env로 2~4h로 조정.
5. **PyJWT 버전 고정**: `pyjwt==2.10.1`. 1.x는 API 호환 안 됨.
6. **PR-H e2e 테스트**: 옵트인 비활성 상태에서 통과 ✓. 활성화 후엔 fixture에 토큰 추가 필요 (별도 PR).
7. **/ws/position/ IoT는 본 작업 범위 밖**: 펌웨어 협업 필요 (별도 sprint).

### 6.3 운영 모니터링 추천
- WS 연결 실패율 (`close code 1008`)
- `BlacklistedToken` 테이블 크기 (정기 cleanup 필요)
- 새 console.warn 메시지 빈도 (Sentry 등 운영 로깅 도구 연동 시)

---

## 7. 트러블슈팅

| 증상 | 원인 가능성 | 해결 |
|---|---|---|
| 모든 WS 연결이 close 1008 | `JWT_SIGNING_KEY` 양쪽 불일치 | 양 서비스 env 비교 + 동일 값 확인 |
| ingest 호출이 401/403 | `INTERNAL_SERVICE_TOKEN` 한쪽만 설정 | drf·fastapi 양쪽 동기화 |
| 사용자가 자주 강제 로그아웃 | refresh 회전 활성 + JS `_refresh` 동시성 회귀 | J12 commit 적용 확인 (`Auth._refreshing` 존재) |
| 1시간마다 사용자 재로그인 요구 | `_refresh` 자동 호출 안 됨 | JS `Auth.apiFetch` 사용 확인 (직접 fetch 사용 자제) |
| `[Menu] icon not defined: ...` 콘솔 warn | 메뉴 트리에 새 icon 키 추가됨 | `shared/layout.js iconMap`에 추가 또는 의도적 무시 |
| `[AppConfig] WS_BASE points to localhost in non-local environment` | 운영 배포에 app_config.html 누락 | Django template 점검 |
| pytest fail | 마이그레이션 미적용 | `python manage.py migrate token_blacklist` |

---

## 8. 분석·실행 보고서 참조

본 브랜치에 포함된 문서:

| 문서 | 내용 | 줄 수 |
|---|---|---|
| `docs/codereviews/2026_05_09/00_overview.md` | 도메인별 리뷰 인덱스 + Top 10 | 176 |
| `docs/codereviews/2026_05_09/01-09, 99_*.md` | 도메인별 11개 보고서 | ~2200 |
| `docs/refactor/js/2026_05_09/00_overview.md` | JS 함수 분석 인덱스 | 228 |
| `docs/refactor/js/2026_05_09/01-06_*.md` | JS 함수 분석 6개 (~75 함수) | ~3500 |
| `docs/refactor/waves/2026_05_09/wave_1.md` | Wave 1 실행 (정합·로깅) | 893 |
| `docs/refactor/waves/2026_05_09/wave_2.md` | Wave 2 실행 (JWT 보안) | 547 |
| `docs/refactor/waves/2026_05_09/wave_3.md` | Wave 3 실행 (WS 인증) | 558 |
| `docs/refactor/waves/2026_05_09/MIGRATION_GUIDE.md` | **본 문서** (적용 가이드) | (이 파일) |
| `docs/phases/team_decisions_summary.md` | Phase 1~4 의사결정 통합 | 630 |

총 docs ~9000줄. 가장 빨리 파악하려면 본 가이드 + 각 wave_N.md의 §1~§3 (개요·변경 항목)만 읽으면 충분합니다.

---

## 9. 머지 결정·다음 단계

### 9.1 머지 권고
- pytest 회귀 0 + 옵트인 패턴 → **머지 안전**
- env 미설정 상태로 머지 가능 (점진적 활성화 가능)

### 9.2 머지 후 즉시 작업
1. PyJWT 의존성 운영 설치
2. token_blacklist 마이그레이션
3. (운영팀 결정) env 활성화 시점

### 9.3 권장 후속 작업 (우선순위)
| 항목 | 시급도 | 규모 |
|---|---|---|
| Wave 1~3 운영 활성화 (env 설정) | 🔴 매우 높음 | 운영 결정만 |
| **B10**: PasswordChangeView 토큰 blacklist | 🟠 중 | 0.5일 |
| AlarmPopup 큐 silent drop 정책 (운영 합의) | 🟠 중 (사고 잠재력 큼) | 1일 + 합의 |
| IoT 장비 인증 (`/ws/position/`) | 🔴 (펌웨어 협업) | 별도 sprint |
| 알람 contract 정합 (alarm-mapper.js) | 🟡 낮음 | 1일 |
| XSS 패턴 정착 (Menu.render createElement) | 🟡 낮음 | 1-2일 |

상세는 [wave_3.md §7](wave_3.md), [99_security_summary.md](../../../codereviews/2026_05_09/99_security_summary.md) 참조.

---

## 10. FAQ

**Q1. env를 설정 안 하고 그냥 머지하면 어떻게 되나요?**
A. 보안 효과 0 + 기존 동작 그대로. 회귀 위험 없음. 단, 코드만 있고 실제 보안은 비활성이라 의미가 약함.

**Q2. JWT_ACCESS_TOKEN_LIFETIME_HOURS=1이 너무 짧으면?**
A. env 변수로 즉시 조정 가능 (e.g. `=4`). 코드 변경 불필요. 양 서비스 동시 적용 권장.

**Q3. 운영에 적용 후 사용자 재로그인은 강제되나요?**
A. **일부 사용자**. ROTATE_REFRESH_TOKENS 도입으로 기존 refresh가 한 번 사용 후 무효화. 사전 공지 권장.

**Q4. /ws/position/은 왜 인증 안 했나요?**
A. IoT 장비 펌웨어 협업 필요. 별도 sprint. 본 작업 범위 밖 명시.

**Q5. 옵트인 비활성 상태에서도 머지 가치가 있나요?**
A. **네**. (1) 다음 활성화 시점에 코드 추가 작업 0 (2) 정합·로깅 효과는 즉시 발생 (3) 분석 산출물 (`docs/`) 자체로 가치.

**Q6. 머지 안 하고 폐기하면?**
A. docs/는 cherry-pick으로 보존 가능. 코드는 수동으로 다른 브랜치로 cherry-pick 가능 (각 commit이 독립적이라 분리 머지도 가능).

---

## 11. 연락·문의

- 분석 산출물: [`docs/codereviews/2026_05_09/`](../../../codereviews/2026_05_09/), [`docs/refactor/js/2026_05_09/`](../../js/2026_05_09/)
- Wave별 상세: [`wave_1.md`](wave_1.md), [`wave_2.md`](wave_2.md), [`wave_3.md`](wave_3.md)
- 본 가이드 작성자에게 직접 문의 (Co-Authored-By 참조)
