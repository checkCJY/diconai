# 리팩토링 통합 PR 검증 체크리스트

> 이 문서는 Phase 1~5를 한 브랜치에 누적 커밋한 뒤 develop으로 PR하기 직전,
> 각 Phase가 의도대로 동작하는지 한 번에 점검하기 위한 마스터 체크리스트입니다.
> 각 Phase 작업 완료 시 해당 섹션을 채우거나 갱신하세요.
>
> 상세 변경 내역은 각 Phase별 `phaseN_*.md` 변경 기록서를 참조.

---

## 진행 상태

| Phase | 제목 | 상태 | 변경 기록서 |
|---|---|---|---|
| 1 | 환경변수·설정 중앙화 + 응답 표준 결정 | ✅ 완료 | [phase1_config_centralization.md](phase1_config_centralization.md) |
| 2 | 어드민 보안 핫픽스 + 페이지네이션 표준화 | ✅ 완료 | [phase2_admin_security_pagination.md](phase2_admin_security_pagination.md) |
| 3 | 프론트 HTTP·WebSocket 통일 | ✅ 완료 | [phase3_frontend_http_ws_unification.md](phase3_frontend_http_ws_unification.md) |
| 4 | drf 레이어 정리 + 예외 핸들러 + Swagger | ⏳ 대기 | — |
| 5 | fastapi 정리 (DRF 클라이언트, 로깅, broadcast 분리) | ⏳ 대기 | — |

---

## 사전 준비 (모든 Phase 검증 공통)

```bash
# 두 서버 가상환경 활성화
cd /home/cjy/diconai/drf-server   && source .venv/bin/activate
cd /home/cjy/diconai/fastapi-server && source .venv/bin/activate

# .env 동기화 (각 서버 폴더에서)
diff .env .env.example   # 빠진 신규 변수 있으면 추가

# Redis · Celery 기동 (별도 터미널)
redis-server
celery -A config worker -l info  # drf-server에서

# 두 서버 기동 (별도 터미널)
python manage.py runserver           # drf 8000
uvicorn app:app --reload --port 8001 # fastapi 8001

# 더미 송출 (별도 터미널, 회귀 확인용)
cd /home/cjy/diconai/fastapi-server
python dummies/gas_dummy.py
python dummies/power_dummy.py
python dummies/position_dummy.py
```

---

## Phase 1 — 환경변수·설정 중앙화 + 응답 표준 결정

### 자동 검증
```bash
# (1) Django check 통과
cd drf-server && python manage.py check
# 기대: System check identified no issues

# (2) Django settings 신규 변수 로드 확인
python -c "
import os; os.environ.setdefault('DJANGO_SECRET_KEY','test')
import django; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()
from django.conf import settings
assert settings.FASTAPI_INTERNAL_URL == 'http://127.0.0.1:8001'
assert settings.FRONTEND_WS_BASE_URL.startswith('ws://')
assert settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds() > 0
print('Phase 1 settings: OK')
"

# (3) fastapi Settings 11개 신규 필드
cd ../fastapi-server && python -c "
from core.config import settings
for k in ['BROADCAST_INTERVAL_SEC','DATA_STALE_THRESHOLD_SEC',
         'POWER_THRESHOLD_CAUTION','POWER_THRESHOLD_DANGER',
         'DUMMY_TARGET_PORT','DUMMY_RISK_PROBABILITY']:
    assert hasattr(settings, k), k
print('Phase 1 fastapi: OK')
"

# (4) 응답 표준 문서 존재
test -f docs/api_response_convention.md && echo "convention OK"

# (5) frontend config 주입 partial 존재
test -f drf-server/templates/components/app_config.html && \
test -f drf-server/static/js/shared/config.js && echo "frontend config OK"
```

### 수동 검증
- [ ] `DJANGO_DEBUG=False`로 실행 시 collectstatic + 기본 라우팅 정상
- [ ] 브라우저 DevTools Console에서 `window.AppConfig` → `{API_BASE, WS_BASE, apiUrl, wsUrl}` 출력
- [ ] `.env`에 `FRONTEND_WS_BASE_URL=ws://다른호스트:8001`로 변경 시 페이지 새로고침 후 `window.AppConfig.WS_BASE`가 갱신됨 (Phase 3에서 실제 사용 시 진가 확인)
- [ ] postgres `DATABASE_URL` 설정 시 sqlite 폴백 미작동 — **운영 전환 시점에 재확인** (개발에선 sqlite 폴백 동작만 확인)

### Breaking change 주의
- `DJANGO_DEBUG`의 *기본값*이 `True` → `False`로 변경됨. `.env`에 `DJANGO_DEBUG=True` 명시 안 되어 있으면 디버그 페이지 안 나옴. **`.env.example`에는 이미 True로 명시됨**.

---

## Phase 2 — 어드민 보안 핫픽스 + 페이지네이션 표준화

### 자동 검증
```bash
cd drf-server && source .venv/bin/activate

# (1) 잔존 무인증 view 검색 — gas_data.py 1건만 나와야 함 (의도적 ingest)
grep -rn "authentication_classes = \[\]\|permission_classes = \[\]" apps/
# 기대: gas_data.py:17-18 만 출력

# (2) 어드민 view 23개 IsSuperAdmin 적용 검증
python -c "
import os; os.environ.setdefault('DJANGO_SECRET_KEY','test')
import django; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()
from apps.core.permissions import IsSuperAdmin
from django.views.generic import TemplateView

modules = [
    ('apps.facilities.views.gas_sensor_admin', [
        'GasSensorAdminListView','GasSensorAdminDetailView','GasSensorAdminBulkDeleteView',
        'DepartmentSelectView','ManagerSelectView','GasSensorNextCodeView',
        'GasSensorConnectionCheckView','GasSensorInspectionListView','GasSensorInspectionActionView']),
    ('apps.facilities.views.power_device_admin', [
        'PowerDeviceAdminListView','PowerDeviceAdminDetailView','PowerDeviceAdminBulkDeleteView',
        'PowerDeviceCodesView','PowerDeviceNextCodeView','PowerDeviceConnectionCheckView',
        'PowerDeviceInspectionListView','PowerDeviceInspectionActionView']),
    ('apps.monitoring.views.gas_data_admin', [
        'GasDataAdminListView','GasDataAdminExportView','GasDataAdminSensorListView']),
    ('apps.monitoring.views.power_data_admin', [
        'PowerDataAdminListView','PowerDataAdminExportView','PowerDataAdminDeviceListView']),
]
import importlib
for mod, names in modules:
    m = importlib.import_module(mod)
    for n in names:
        cls = getattr(m, n)
        assert IsSuperAdmin in cls.permission_classes, f'{mod}.{n} missing IsSuperAdmin'
print('Phase 2 auth: 23 views OK')

# PageView 3개가 TemplateView
from apps.facilities.views.gas_sensor_admin import GasSensorAdminPageView
from apps.facilities.views.power_device_admin import PowerDeviceAdminPageView
from apps.facilities.views.facility_admin import FacilityAdminPageView
for cls in (GasSensorAdminPageView, PowerDeviceAdminPageView, FacilityAdminPageView):
    assert issubclass(cls, TemplateView), cls.__name__
print('Phase 2 pages: 3 TemplateViews OK')

# AdminPagination 5키
from apps.core.pagination import AdminPagination
import inspect
src = inspect.getsource(AdminPagination.get_paginated_response)
for k in ['results','total','page','page_size','has_next']:
    assert k in src, k
print('Phase 2 pagination: 5 keys OK')
"
```

### 수동 검증 (브라우저 + curl)
- [ ] 슈퍼관리자 로그인 → 어드민 패널 14개 페이지 정상 진입
  - `/admin-panel/accounts-management/`
  - `/admin-panel/organizations/`
  - `/admin-panel/geofence/`
  - `/admin-panel/map-editor/`
  - `/admin-panel/facility/`
  - `/admin-panel/gas-sensors/`
  - `/admin-panel/data/gas/`
  - `/admin-panel/data/power/`
- [ ] 슈퍼관리자 어드민 패널에서 가스 센서·전력 장비 CRUD 정상 (목록·등록·수정·삭제)
- [ ] **권한 차단 확인**: 토큰 없이 `curl http://localhost:8000/api/admin/gas-sensors/` → 401
- [ ] **권한 차단 확인**: 일반 작업자 토큰으로 동일 호출 → 403
- [ ] DevTools Network에서 페이지네이션 응답 5키 (`results`, `total`, `page`, `page_size`, `has_next`) 확인
- [ ] **회귀 확인**: 더미 송출 시 `/api/monitoring/gas/`, `/api/monitoring/power/event/` 등 ingest 엔드포인트 무인증 정상 수신 (서버-서버 호출 보존)

### Breaking change 주의
- 어드민 API 23개가 **무인증 → 슈퍼관리자 필수**. 외부 도구로 토큰 없이 호출하던 사용 사례 점검 필요.
- 일반 작업자 권한으로 어드민 호출하던 코드 → 403 발생.

---

## Phase 3 — 프론트 HTTP·WebSocket 통일

### 자동 검증
```bash
cd /home/cjy/diconai/drf-server/static/js

# (1) 하드코딩된 WS URL 잔존 — config.js의 fallback 1건만 허용
grep -rn "ws://127.0.0.1\|http://localhost:8001\|http://127.0.0.1:8001" --include="*.js"
# 기대: shared/config.js:8 (WS_BASE fallback) 1건만

# (2) 수동 Authorization 헤더 — 0건이어야 함
grep -rn "Authorization.*Bearer" --include="*.js" | grep -v "shared/auth.js"
# 기대: 0건

# (3) localStorage 직접 접근 (Auth 외부) — 0건
grep -rn "localStorage\.\(getItem\|setItem\|removeItem\)" --include="*.js" | grep -v "shared/auth.js"
# 기대: 0건

# (4) _authHeaders 헬퍼 잔존 — 0건
grep -rn "_authHeaders" --include="*.js"
# 기대: 0건

# (5) Auth.getAccessToken 직접 사용 — layout.js + login.js 2건만 허용 (토큰 존재 검사용)
grep -rn "Auth\.getAccessToken" --include="*.js" | grep -v shared/auth.js | grep -v shared/ws-client.js
# 기대: layout.js:233, login.js:3 두 곳만

# (6) ws-client.js 신설 확인
test -f shared/ws-client.js && echo "ws-client OK"

# (7) Django check
cd /home/cjy/diconai/drf-server && python manage.py check
# 기대: System check identified no issues
```

### 수동 검증 (브라우저 실측)
- [ ] **JWT 자동 refresh:** 짧은 JWT lifetime(예: 1분)로 발급 → 어드민 CRUD 도중 만료 → 자동 refresh로 작업 연속성 유지
- [ ] **WS 중복 연결 제거:** DevTools Network → WS 탭에서 `/ws/sensors/` 연결 **1개만** (이전: alarm-ws + dashboard 2개)
- [ ] **WS_BASE 운영 전환:** `.env` `FRONTEND_WS_BASE_URL`을 다른 호스트로 변경 → 페이지 새로고침 시 새 호스트로 연결
- [ ] **로그인 리다이렉트:** 토큰 없이 어드민 페이지 진입 → 모든 화면이 일관되게 `/accounts/login/`으로 이동
- [ ] **회귀 — admin 8개 페이지:** accounts, facility, gas_sensor, power_system, geofence, map_editor, organizations, data 가스/전력 모두 CRUD 정상
- [ ] **회귀 — dashboard 메인:** 가스/전력/위치 실시간 갱신, 알람 팝업, 지도 패널 정상
- [ ] **회귀 — detail 5개:** `/dashboard/monitoring/{realtime,gas,power,workers,events}/` 정상
- [ ] **회귀 — safety:** VR 진행률 저장/복원 정상, 안전 점검 체크리스트 정상

### Breaking change 주의
- **없음**(non-breaking). 단, 18개 JS 파일 수정의 회귀 가능성으로 위 수동 검증 시나리오를 모두 돌려보는 게 안전.

---

## Phase 4 — drf 레이어 정리 + 예외 핸들러 + Swagger (예정)

### 자동 검증 (예정)
```bash
# (1) view에 ORM 직접 호출이 사라졌는지 (selectors로 추출됨)
grep -rn "\.filter(\|\.annotate(\|\.order_by(" drf-server/apps/*/views/ \
  | grep -v "test_" | grep -v "/admin.py"
# 기대: 거의 0건 (selectors/services에서만 호출)

# (2) 마이그레이션 누락 없음
cd drf-server && python manage.py makemigrations --check --dry-run
# 기대: No changes detected

# (3) Swagger 엔드포인트 등록
python -c "
import os; os.environ.setdefault('DJANGO_SECRET_KEY','test')
import django; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()
from django.urls import resolve
resolve('/api/schema/')
resolve('/api/schema/swagger-ui/')
print('Swagger URLs OK')
"

# (4) selectors / services 패키지가 비어있지 않음
ls drf-server/apps/accounts/selectors/  drf-server/apps/accounts/services/
ls drf-server/apps/facilities/selectors/ drf-server/apps/facilities/services/
```

### 수동 검증 (예정)
- [ ] `/api/schema/swagger-ui/` 접속 → 모든 엔드포인트 schema 노출
- [ ] 사용자 생성 도중 강제 IntegrityError → 부분 커밋 없음 (트랜잭션 동작)
- [ ] 잘못된 입력으로 검증 실패 호출 → 응답이 `{error: {code: "validation_failed", message, details}}` 구조
- [ ] 인증 실패 시 응답이 `{error: {code: "authentication_required", ...}}`
- [ ] 어드민 패널 화면 14개 회귀 (selector 추출 후에도 동일 동작)
- [ ] `apps/accounts/views/admin_views.py`의 dead code (`AccountsAdminPageView` APIView 버전, `OrganizationsAdminPageView` APIView 버전) 제거 확인

---

## Phase 5 — fastapi 정리 (예정)

### 자동 검증 (예정)
```bash
# (1) print() 잔존 0건
grep -rn "^\s*print(" fastapi-server/ --include="*.py" | grep -v dummies/ | grep -v __pycache__
# 기대: 0건 (dummies는 CLI 출력 허용)

# (2) Celery → fastapi 호출에 settings 사용
grep -n "127.0.0.1:8001\|localhost:8001" drf-server/apps/alerts/tasks.py
# 기대: 0건 (settings.FASTAPI_INTERNAL_URL 사용)

# (3) broadcast.py 함수 분할 확인
python -c "
from websocket.services import broadcast
required = ['is_stale', 'assemble_payload']
for fn in required:
    assert hasattr(broadcast, fn), fn
print('broadcast split OK')
"

# (4) drf_client.py 신설 확인
test -f fastapi-server/services/drf_client.py && echo "drf_client OK"

# (5) Swagger UI에 모든 엔드포인트
curl -s http://localhost:8001/openapi.json | python -c "
import json, sys
spec = json.load(sys.stdin)
paths = list(spec['paths'].keys())
expected = ['/api/sensors/gas', '/api/power/onoff', '/api/positioning/receive', '/internal/alarms/push/']
for e in expected:
    assert any(e in p for p in paths), e
print(f'OpenAPI paths: {len(paths)} OK')
"
```

### 수동 검증 (예정)
- [ ] 더미 3종 동시 송출 + DRF 강제 종료(`Ctrl+C`) → fastapi 죽지 않고 broadcast 계속, logger.error 출력
- [ ] DRF 재기동 → 자동 회복, 알람 정상 생성
- [ ] `/docs` (FastAPI Swagger UI) 모든 엔드포인트 schema 표시
- [ ] WS 클라이언트가 동일 페이로드 수신 (회귀)
- [ ] stale 판정 동작 (센서 데이터 8초 이상 미수신 → `stale: true` 표시)
- [ ] 서버-서버 ingest 엔드포인트 보호 확인:
  - localhost 외부에서 `/api/monitoring/gas/` 호출 → 차단됨
  - localhost(fastapi)에서 호출 → 정상

---

## End-to-End 통합 검증 (PR 직전 1회)

모든 Phase 적용 후 다음 시나리오를 한 번에 돌려서 회귀 없음을 최종 확인합니다.

### 기동
- [ ] redis-server, celery worker, drf-server (8000), fastapi-server (8001) 모두 정상 기동
- [ ] dummies 3종 (gas, power, position) 동시 실행

### 슈퍼관리자 시나리오
- [ ] `/accounts/login/` → 슈퍼관리자 로그인 → JWT 발급 (DevTools localStorage)
- [ ] `/dashboard/` → 메인 대시보드 정상 (가스/전력/위치 실시간 갱신, 알람 팝업)
- [ ] 좌측 SNB → 모니터링 페이지 5개(realtime, gas, power, workers, events) 모두 정상
- [ ] `/admin-panel/...` 페이지 8개 모두 정상 진입 + 페이지네이션 UI에서 다음 페이지 / has_next=false 정상 처리
- [ ] 어드민 패널에서 가스 센서·전력 장비·사용자·조직·지오펜스 CRUD 모두 정상

### 일반 작업자 시나리오
- [ ] 일반 작업자 계정으로 로그인 → `/dashboard/` 정상 진입
- [ ] `/admin-panel/...` 직접 진입 → 페이지 진입은 가능(HTML 셸)하지만 API 호출이 403 → 적절한 안내/리다이렉트
- [ ] 작업자 본인 위치·알람만 수신되는지 (worker_clients 개인 전송)

### 토큰 만료·갱신
- [ ] JWT lifetime을 1분으로 단축하고 어드민 CRUD 진행 → 만료 시점에 자동 refresh로 작업 연속성 유지

### 장애 회복
- [ ] DRF 강제 종료 → fastapi 살아있음, broadcast 지속
- [ ] DRF 복구 → 알람·이벤트 정상 생성

### 운영 환경 전환 시뮬
- [ ] `.env` `DJANGO_DEBUG=False`, `FRONTEND_WS_BASE_URL=ws://다른호스트:8001`로 변경 → 두 서버 재기동 → 라우팅·정적파일·WS 연결 모두 정상

### 코드 위생 최종 점검
```bash
# print() 잔존 (fastapi)
grep -rn "^\s*print(" fastapi-server/ --include="*.py" | grep -v dummies/

# 무인증 view 잔존 (drf)
grep -rn "authentication_classes = \[\]" drf-server/apps/

# 하드코딩 URL 잔존
grep -rn "ws://127.0.0.1:8001\|http://127.0.0.1:8001\|http://localhost:8001" \
  drf-server/static/js/ drf-server/apps/ fastapi-server/

# pre-commit
cd /home/cjy/diconai && pre-commit run --files $(git diff develop --name-only)
```

---

## PR 직전 최종 점검 표

| 항목 | 확인 |
|---|---|
| Phase 1~5 모든 자동 검증 명령 통과 | ☐ |
| End-to-End 통합 검증 시나리오 통과 | ☐ |
| 각 Phase별 changelog 문서 최신 상태 | ☐ |
| `.env`/`.env.example` 동기화 (신규 변수 누락 없음) | ☐ |
| `git status` 깨끗 (untracked 잔존 0) | ☐ |
| 의도치 않은 파일 커밋 (db.sqlite3, .env, *.log) 없음 | ☐ |
| pre-commit (ruff, formatter) 통과 | ☐ |
| Breaking change 영향 영역 PR 본문에 명시 | ☐ |
| 마이그레이션 가이드(서비스 운영자용) PR 본문 또는 changelog에 포함 | ☐ |
| 의도적으로 미룬 항목·후속 작업 명시 | ☐ |

---

## 변경 이력

- 2026-05-04 — 초안. Phase 1·2 검증 항목 채움. Phase 3·4·5는 작업 진행 시 갱신.
