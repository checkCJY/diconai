# 변경 기록서 — Phase1 환경변수·설정 중앙화 + 응답 표준 결정

> 작성일: 2026-05-04
> 브랜치: feature/refactor-phase1-config-central (예정 — 현재 작업 브랜치 feature/watt_alarm_test)
> 작업 종류: refactor + decision
> 하위 호환성: **non-breaking** — 모든 신규 env에 기본값이 있어 기존 `.env`만 가진 환경에서도 변경 없이 동작

---

## 1. 변경 개요

- **목적(Why):** 코드 리뷰 우려사항 문서(`.claude/skills/diconai/0503_코드리뷰시 참고해야 할 사항들.md`)에서 지적된 "환경변수 하드코딩"과 "코드 패턴 불일치"의 *전제 조건*을 정리. 후속 Phase 2(백엔드 보안·페이지네이션 표준화) 및 Phase 3(프론트 HTTP·WS 통일)이 마이그레이션 타깃으로 사용할 응답 봉투 표준도 함께 결정.
- **결과(What):** (1) drf-server `DEBUG`·DB URL·JWT 수명·FastAPI URL·프론트 노출용 URL 등 8종 신규 env 도입. (2) fastapi-server `Settings`에 11종 신규 env(임계치·broadcast 주기·stale 임계·더미 송출 파라미터). (3) 프론트 `window.AppConfig` 메커니즘 신설 — 모든 base 템플릿이 서버사이드 렌더 시 API/WS 베이스를 주입. (4) `docs/api_response_convention.md` — Phase 2/3 마이그레이션 타깃이 될 응답 봉투 5키 표준과 에러 `{error: {code, message}}` 표준 결정.
- **영향 범위(Where):** drf-server(설정 + 템플릿 + 신규 context processor) / fastapi-server(설정) / 프론트엔드(템플릿 11개 + shared/config.js 신설) / 인프라(.env 운영).

## 2. Before / After 비교

| 구분 | Before | After |
|---|---|---|
| Django `DEBUG` | `DEBUG = True` 하드코딩 | `DEBUG = env.bool("DJANGO_DEBUG", default=False)` — 운영 안전 기본값 |
| Django DB | sqlite 경로 하드코딩 | `env.db("DATABASE_URL", default=sqlite://...)` — postgres 운영 전환 가능 |
| JWT 수명 | `timedelta(hours=24)` 하드코딩 | `env.int("JWT_ACCESS_TOKEN_LIFETIME_HOURS", default=24)` |
| Celery → FastAPI 호출 URL | `apps/alerts/tasks.py`에서 `http://127.0.0.1:8001` 하드코딩 (Phase 5에서 적용 예정) | `settings.FASTAPI_INTERNAL_URL` 도입 (참조처 변경은 Phase 5에서) |
| 프론트 WS URL | JS 파일 7곳에서 `ws://127.0.0.1:8001/...` 하드코딩 | `window.AppConfig.WS_BASE` 도입 (참조처 변경은 Phase 3에서) |
| fastapi 임계치 | `core/power_thresholds.py` 코드 상수 | `settings.POWER_THRESHOLD_CAUTION/DANGER` 참조 (값 동일 유지) |
| fastapi broadcast 주기 | `app.py`의 `asyncio.sleep(5)` 하드코딩 (Phase 5에서 적용 예정) | `settings.BROADCAST_INTERVAL_SEC` 도입 |
| 응답 봉투 표준 | 페이지네이션이 `results` / `records` 혼재, 에러 응답 형식 불통일 | `docs/api_response_convention.md`에서 `{results,total,page,page_size,has_next}` 5키 + `{error:{code,message}}` 결정 (마이그레이션은 Phase 2/4) |

## 3. 변경 파일 목록

### 신규
| 파일 | 역할 |
|---|---|
| `docs/api_response_convention.md` | Phase 2/3/4/5 마이그레이션 타깃이 될 응답 봉투 표준 결정문서 |
| `docs/changelog/phase1_config_centralization.md` | 본 문서 |
| `drf-server/apps/core/context_processors.py` | `frontend_config` — 모든 템플릿에 `FRONTEND_API_BASE_URL`, `FRONTEND_WS_BASE_URL` 주입 |
| `drf-server/templates/components/app_config.html` | 인라인 `<script>`로 `window.AppConfig` 정의하는 partial |
| `drf-server/static/js/shared/config.js` | `window.AppConfig` fallback + `apiUrl()`/`wsUrl()` 헬퍼 |
| `fastapi-server/.env.example` | fastapi env 템플릿 (11종 변수) |

### 수정
| 파일 | 변경 요약 |
|---|---|
| `drf-server/config/settings.py` | `DEBUG`/`DATABASE_URL`/JWT 수명을 env로, `FASTAPI_INTERNAL_URL`·`FRONTEND_API_BASE_URL`·`FRONTEND_WS_BASE_URL` 추가, context processor 등록 |
| `drf-server/.env.example` | 신규 env 8종 추가 (DJANGO_DEBUG, DATABASE_URL, REDIS_URL, JWT 2종, FASTAPI_INTERNAL_URL, FRONTEND 2종) |
| `drf-server/templates/admin_panel/base.html` | `app_config.html` include + `config.js` 로드 (auth.js 직전) |
| `drf-server/templates/dashboard/main.html` | 동상 |
| `drf-server/templates/auth/login.html` | 동상 |
| `drf-server/templates/snb_details/*.html` (10개) | sed 일괄 적용 — `event_detail`, `monitoring_events`, `monitoring_gas`, `monitoring_power`, `monitoring_realtime`, `monitoring_workers`, `my_profile`, `safety_checklist`, `safety_history`, `safety_vr` |
| `fastapi-server/core/config.py` | `Settings`에 11개 필드 추가 (DRF 타임아웃, broadcast 주기, stale 임계, 전력 임계치 2종, 더미 4종) |
| `fastapi-server/core/power_thresholds.py` | `settings`에서 값 가져오도록 변경 (기존 import 경로 `POWER_THRESHOLDS` dict 그대로 유지) |

### 삭제
해당 없음.

## 4. API / 응답 / 인터페이스 변경
**런타임 API 변경 없음.** 본 단계는 *결정문서 작성*과 *설정 인프라 정비*만 수행. 응답 봉투 표준의 실제 적용(페이지네이션 키 통일, 글로벌 예외 핸들러)은 Phase 2/4에서 진행.

## 5. 환경변수·설정 변경

### drf-server (.env)

| 변수 | 추가/변경 | 기본값 | 설명 |
|---|---|---|---|
| `DJANGO_DEBUG` | 추가 | `False` | 운영 안전 기본값. 개발 환경은 `.env`에서 `True` 명시 |
| `DATABASE_URL` | 추가 | `sqlite:///<BASE_DIR>/db.sqlite3` | 미설정 시 sqlite 폴백. 운영 `postgres://...` |
| `JWT_ACCESS_TOKEN_LIFETIME_HOURS` | 추가 | `24` | |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | 추가 | `30` | |
| `FASTAPI_INTERNAL_URL` | 추가 | `http://127.0.0.1:8001` | Celery → FastAPI WS 브리지 호출 (Phase 5 적용) |
| `FRONTEND_API_BASE_URL` | 추가 | `""` (빈 문자열 = same-origin) | 브라우저 노출. 운영에서 fastapi가 다른 도메인이면 지정 |
| `FRONTEND_WS_BASE_URL` | 추가 | `ws://127.0.0.1:8001` | 브라우저 WebSocket 베이스 |

### fastapi-server (.env)

| 변수 | 추가/변경 | 기본값 | 설명 |
|---|---|---|---|
| `DRF_REQUEST_TIMEOUT_SEC` | 추가 | `5.0` | DRF httpx 호출 타임아웃 (Phase 5 적용) |
| `BROADCAST_INTERVAL_SEC` | 추가 | `5.0` | WS broadcast 주기 (Phase 5 적용) |
| `DATA_STALE_THRESHOLD_SEC` | 추가 | `8.0` | stale 판정 임계 (Phase 5 적용) |
| `POWER_THRESHOLD_CAUTION` | 추가 | `2200` | 전력 주의 임계치 (W) |
| `POWER_THRESHOLD_DANGER` | 추가 | `2860` | 전력 위험 임계치 (W) |
| `DUMMY_TARGET_HOST` | 추가 | `127.0.0.1` | 더미 송출 대상 호스트 (Phase 5 적용) |
| `DUMMY_TARGET_PORT` | 추가 | `8001` | 더미 송출 대상 포트 |
| `DUMMY_SEND_INTERVAL_SEC` | 추가 | `1.0` | 더미 송출 주기 |
| `DUMMY_RISK_PROBABILITY` | 추가 | `0.1` | 임계치 초과 케이스 발생 확률 |

> **참고:** "Phase 5 적용"으로 표시된 항목은 본 Phase 1에서 *Settings 필드 정의만* 추가했고, 실제 코드 참조처 변경은 Phase 5에서 수행. 본 단계는 후속 작업 인프라만 정비.

## 6. 마이그레이션 가이드

```bash
# 1. 풀 받기
git pull

# 2. drf-server .env에 신규 변수 추가 (기본값으로 동작하므로 필수 아님, 권장)
cd drf-server
diff .env .env.example  # 신규 변수 확인
# 필요 시 .env에 누락된 변수 복사

# 3. fastapi-server .env 생성 또는 갱신
cd ../fastapi-server
[ -f .env ] || cp .env.example .env

# 4. 의존성 변경 없음 — pip install 불필요

# 5. DB 마이그레이션 변경 없음 — makemigrations 불필요

# 6. 서버 재시작
cd ../drf-server && python manage.py runserver         # 8000
cd ../fastapi-server && uvicorn app:app --reload --port 8001
```

**기존 `.env`를 그대로 둬도 동작함** — 모든 신규 env에 기본값 존재.

## 7. 결정 근거 (ADR)

| 결정 | 채택안 | 검토했던 대안 | 근거 |
|---|---|---|---|
| 가스 임계치 env화 여부 | **미적용** (코드 상수 유지) | env로 옮기기 (25개 중첩값) | 산업안전보건법 규제값 → 환경별 변동 부적절. 25개 중첩값을 평탄한 env로 펴면 가독성 저하. |
| CORS 설정 추가 | **미적용** | django-cors-headers 도입 | 현재 의존성에 없음. 브라우저는 fastapi와 WebSocket으로만 통신해 CORS preflight 불필요. fastapi가 HTTP API를 노출하게 되면 그때 추가. |
| `config.js` 위치 | **static + 인라인 partial 조합** | (a) 순수 static js, (b) Django view로 동적 렌더, (c) 인라인 only | static에는 fallback과 헬퍼만 두고 *주입은 인라인 partial*로 처리. 빌드 파이프라인 없는 vanilla JS 환경에서 가장 단순하고, 다른 shared 모듈이 `window.AppConfig.apiUrl()` 등 헬퍼를 일관되게 호출 가능. |
| 응답 봉투 페이지네이션 키 | **`{results,total,page,page_size,has_next}`** | DRF 기본 `{count,next,previous,results}`, 또는 기존 `{records,...}` 유지 | 기존 코드에 `results`와 `records`가 모두 존재. `results`로 통일하면 DRF `AdminPagination`(이미 `accounts/admin_views.py`가 사용 중)과도 자연스럽게 일치. URL 기반 `next/previous`는 SPA가 아니라 페이지 번호 기반 UI에 불필요해 `has_next` boolean으로 대체. |
| 에러 응답 봉투 | **`{error: {code, message, details?}}`** | 평면 `{ok:false, msg}` 또는 RFC 7807 `application/problem+json` | 기존 코드의 일부 `{ok:false}` 패턴은 200 + ok=false 안티패턴을 동반. RFC 7807은 좋지만 클라이언트 학습 비용. `error` 객체 1단 wrap이 가장 단순하면서 code/message 분리로 i18n·기계 처리 모두 가능. |
| 변경기록 프롬프트 | **`system_instruction.md`(신규기능) + `system_instruction_changelog.md`(변경기록) 분리** | 단일 프롬프트에 type 분기, 양식 자유화 | 신규 기능 spec(SNB-04/05)이 이미 정착되어 있어 건드리면 회귀 위험. 변경 기록은 다른 항목(Before/After, 마이그레이션 가이드, ADR)이 필요하므로 별도 프롬프트가 명확. |

## 8. 검증 방법 / 결과

```bash
# (1) Django 설정 import 검증
cd drf-server && source .venv/bin/activate
python -c "
import os; os.environ.setdefault('DJANGO_SECRET_KEY','test')
import django; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()
from django.conf import settings
assert settings.FASTAPI_INTERNAL_URL == 'http://127.0.0.1:8001'
assert settings.FRONTEND_WS_BASE_URL == 'ws://127.0.0.1:8001'
"
# 결과: ✅ 통과

# (2) Django check
python manage.py check
# 결과: ✅ System check identified no issues (0 silenced).

# (3) fastapi Settings import
cd ../fastapi-server && source .venv/bin/activate
python -c "from core.config import settings; print(settings.POWER_THRESHOLD_CAUTION)"
# 결과: ✅ 2200

# (4) 기존 power_thresholds 호환
python -c "from core.power_thresholds import POWER_THRESHOLDS; print(POWER_THRESHOLDS)"
# 결과: ✅ {'caution': 2200, 'danger': 2860}
```

### 검증 미완 (후속 Phase로 이월)
- [ ] 실제 브라우저에서 `window.AppConfig` 노출 확인 → Phase 2 PR 머지 후 첫 실행 때 함께
- [ ] `DJANGO_DEBUG=False`로 collectstatic + 라우팅 동작 확인 → 실제 배포 시점
- [ ] postgres `DATABASE_URL` 동작 확인 → 운영 환경 전환 시점

## 9. 하위 호환성 / 롤백

- **하위 호환성: non-breaking.** 모든 신규 env에 기본값 존재. 기존 `.env`를 그대로 둬도 동일 동작.
- **단, `DJANGO_DEBUG`의 *기본값*이 `False`로 바뀜** — `.env`에 `DJANGO_DEBUG=True`가 없으면 디버그 페이지가 안 나오고 `ALLOWED_HOSTS`가 엄격하게 적용된다. 기존 `.env.example`에 이미 `DJANGO_DEBUG=True`가 있어 신규 setup에는 영향 없음. 기존 개발 환경의 `.env`에 `DJANGO_DEBUG=True`가 없으면 추가 필요.
- **롤백:** `git revert <SHA>`로 충분. DB 변경 없음, 의존성 변경 없음.

## 10. 후속 작업 / 참고

### 본 Phase에서 의도적으로 미룬 것
- `apps/alerts/tasks.py`의 하드코딩된 `http://127.0.0.1:8001` → `settings.FASTAPI_INTERNAL_URL` 참조 변경 — **Phase 5**
- `fastapi-server/app.py`의 broadcast 주기 하드코딩 → `settings.BROADCAST_INTERVAL_SEC` 참조 변경 — **Phase 5**
- 프론트 JS 7곳의 하드코딩 WS URL → `AppConfig.WS_BASE` 참조 변경 — **Phase 3**
- 프론트 fetch 호출 14+곳의 하드코딩 API URL → `AppConfig.apiUrl()` 또는 `Auth.apiFetch` 사용 — **Phase 3**
- 페이지네이션 응답 키 `records` → `results` 통일 — **Phase 2**
- 글로벌 예외 핸들러로 `{error:{code,message}}` 자동 변환 — **Phase 4**(DRF), **Phase 5**(FastAPI)

### 관련 문서
- 리팩토링 마스터 플랜: `~/.claude/plans/streamed-sparking-dongarra.md`
- 응답 봉투 표준: `docs/api_response_convention.md`
- 사용자 코드리뷰 우려사항: `.claude/skills/diconai/0503_코드리뷰시 참고해야 할 사항들.md`
- 변경기록 프롬프트: `skill/system_instruction_changelog.md`
- 신규기능 프롬프트: `skill/system_instruction.md` (시스템 정보 정정 포함)
