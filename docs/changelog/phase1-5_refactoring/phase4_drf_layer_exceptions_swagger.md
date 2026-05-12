# 변경 기록서 — Phase4 drf-server 레이어 정리 + 전역 예외 핸들러 + Swagger

> 작성일: 2026-05-04
> 브랜치: feature/project_4_refactoring
> 작업 종류: refactor + feat
> 하위 호환성: **breaking (응답 형식)** — 4xx/5xx 에러 응답이 `{detail: ...}` → `{error: {code, message, details?}}`로 변경됨. 기존 프론트가 `data.detail`을 직접 읽고 있다면 깨짐. 200 응답 본문은 그대로.

---

## 1. 변경 개요

- **목적(Why):** view 14곳에서 ORM(`.filter`/`.annotate`/`.order_by`) 직접 호출이 난립해 selectors 패키지가 비어있었고, 다중 모델 쓰기가 일어나는 view들(사용자 생성, 센서/장비 생성·수정)에 트랜잭션이 누락되어 부분 커밋 위험이 있었으며, 4xx/5xx 응답 형식이 표준 결정문서(Phase 1 `docs/api_response_convention.md`)와 어긋나 있었음. 또 OpenAPI 명세가 자동 생성되지 않아 Phase 3 프론트 통일과 운영 환경 통합이 어려운 상태.
- **결과(What):** (1) `accounts/selectors/admin_users.py`와 `facilities/selectors/admin_devices.py` 신설로 어드민 패널 List view 3곳의 검색·필터·정렬 로직을 selector로 추출. (2) `apps/core/exceptions.py`에 글로벌 예외 핸들러 등록 → 모든 4xx/5xx 응답이 `{error:{code,message}}` 표준 봉투로 자동 변환. (3) `drf-spectacular` 도입 → `/api/schema/` (OpenAPI YAML), `/api/schema/swagger-ui/` (Swagger UI), `/api/schema/redoc/`(ReDoc) 노출. (4) 다중 쓰기 view 6곳에 `@transaction.atomic` 적용. (5) 어드민 view 묵음 `except Exception: ok=False` 패턴 2곳을 구체 예외(`OSError`) + logging으로 교체. (6) `admin_views.py`의 dead code 2개 클래스 제거.
- **영향 범위(Where):** drf-server 백엔드만 (응답 형식 변경은 프론트 영향 — 다음 단계에서 검증 필요).

## 2. Before / After 비교

| 구분 | Before | After |
|---|---|---|
| 어드민 사용자 목록 view | view에서 `.prefetch_related().filter().filter()...order_by()` 40줄 직접 호출 | `list_admin_users(name=, ..., sort=)` selector 호출 1줄 |
| 어드민 가스/전력 장비 view | view에서 검색 분기 + Case/When + priority annotate 50줄 직접 작성 | `list_admin_gas_sensors(...)` / `list_admin_power_devices(...)` selector 호출 1줄 |
| 4xx/5xx 응답 형식 | DRF 기본 `{"detail": "..."}` 또는 view마다 다른 형식 (`{"error": "..."}`, `{"detail": "..."}`) | **`{"error": {"code", "message", "details?"}}` 통일** |
| 401 응답 (예) | `{"detail": "자격 인증 데이터가 제공되지 않았습니다."}` | `{"error": {"code": "authentication_required", "message": "자격 인증 데이터가 제공되지 않았습니다."}}` |
| 검증 실패 응답 (예) | `{"name": ["이 필드는 필수입니다."]}` | `{"error": {"code": "validation_failed", "message": "이 필드는 필수입니다.", "details": {"name": ["이 필드는 필수입니다."]}}}` |
| OpenAPI 문서 | 없음 | `/api/schema/`, `/api/schema/swagger-ui/`, `/api/schema/redoc/` 노출 (78개 path 자동 인덱싱) |
| 다중 쓰기 view 트랜잭션 | 없음 — 부분 커밋 위험 | `@transaction.atomic` 적용 (사용자 생성·수정, 가스 센서·전력 장비 생성·수정, Equipment 수정[+PowerDevice 재활성화]) |
| 묵음 예외 처리 | `except Exception: ok = False` (gas/power connection_check) | `except OSError as exc: logger.warning(...); ok = False` |
| dead code | `admin_views.py`의 `AccountsAdminPageView`/`OrganizationsAdminPageView` (APIView+render, 어디서도 import 안 됨) | 제거 (admin_panel_urls.py의 동명 TemplateView가 실제 사용됨) |

### 코드 차이 예시

```python
# Before (admin_views.py:47-93)
def get(self, request):
    qs = (
        User.objects.prefetch_related("dept_memberships__department")
        .select_related("position").all()
    )
    name = request.query_params.get("name", "").strip()
    department_id = request.query_params.get("department")
    # ... 5개 더
    if name: qs = qs.filter(name__icontains=name)
    if department_id: qs = qs.filter(...)
    # ... 30줄 더
    sort_map = {"name_asc": "name", ...}
    qs = qs.order_by(sort_map.get(sort, "name"))
    paginator = AdminPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = AccountsAdminListSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)

# After
def get(self, request):
    qs = list_admin_users(
        name=request.query_params.get("name", ""),
        department_id=request.query_params.get("department"),
        position_id=request.query_params.get("position"),
        user_type=request.query_params.get("user_type"),
        account_status=request.query_params.get("status"),
        sort=request.query_params.get("sort", "name_asc"),
    )
    paginator = AdminPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = AccountsAdminListSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)
```

## 3. 변경 파일 목록

### 신규 (3개)
| 파일 | 역할 |
|---|---|
| `drf-server/apps/core/exceptions.py` | DRF `EXCEPTION_HANDLER` 글로벌 핸들러. `default_code` → 응답 봉투 표준 `code` 매핑, HTTP status 폴백, 미처리 예외 500 표준 응답 + logging.exception |
| `drf-server/apps/accounts/selectors/admin_users.py` | `list_admin_users(name=, department_id=, position_id=, user_type=, account_status=, sort=)` — 화이트리스트 sort + prefetch_related/select_related 정책 일원화 |
| `drf-server/apps/facilities/selectors/admin_devices.py` | `list_admin_gas_sensors(...)`, `list_admin_power_devices(...)` — 가스/전력 공통 검색·필터(`_apply_common_filters`) + 이상 상태 우선 정렬(`_apply_priority_order`) 추출 |

### 수정 (7개)
| 파일 | 변경 요약 |
|---|---|
| `drf-server/requirements.txt` | `drf-spectacular==0.29.0` + 트랜시티브(attrs, inflection, jsonschema-specifications, pyyaml, referencing, rpds-py, uritemplate) 추가 |
| `drf-server/config/settings.py` | `INSTALLED_APPS`에 `drf_spectacular`, `REST_FRAMEWORK`에 `EXCEPTION_HANDLER`/`DEFAULT_SCHEMA_CLASS`, 신규 `SPECTACULAR_SETTINGS` 블록, **`LOGGING` dictConfig + `DJANGO_LOG_LEVEL` env 추가** (포맷: `시간 LEVEL 모듈: [CATEGORY] key=value`) |
| `drf-server/.env.example` | `DJANGO_LOG_LEVEL=INFO` 추가 |
| `drf-server/config/urls.py` | `/api/schema/`, `/api/schema/swagger-ui/`, `/api/schema/redoc/` 라우트 추가 |
| `drf-server/apps/accounts/views/admin_views.py` | List view를 selector 호출로 단순화, `@transaction.atomic` POST/PATCH 적용, dead `AccountsAdminPageView`·`OrganizationsAdminPageView`(APIView 버전, dead) 제거. 에러 응답 키 `error` → `detail` (글로벌 핸들러가 표준 봉투로 감싸므로 일관성 위해) |
| `drf-server/apps/facilities/views/gas_sensor_admin.py` | List view selector 호출, POST/PUT `@transaction.atomic`, `connection_check`의 `except Exception` → `except OSError + logger.warning` |
| `drf-server/apps/facilities/views/power_device_admin.py` | 동상 |
| `drf-server/apps/facilities/views/facility_admin.py` | `EquipmentAdminDetailView.put`(다중 모델 쓰기: Equipment 저장 + PowerDevice 재활성화)에 `@transaction.atomic` 적용 |

### 삭제 (코드 블록)
- `apps/accounts/views/admin_views.py` 220-249줄의 `AccountsAdminPageView`(APIView), `OrganizationsAdminPageView`(APIView) 클래스 삭제 (admin_panel_urls.py에 동명 TemplateView가 별도로 존재해 실제 사용됨; APIView 버전은 import 추적 결과 어디서도 사용 안 됨)

## 4. API / 응답 / 인터페이스 변경

### Breaking — 4xx/5xx 응답 형식 통일

```diff
- HTTP 401
- {"detail": "자격 인증 데이터가 제공되지 않았습니다."}
+ HTTP 401
+ {"error": {"code": "authentication_required", "message": "자격 인증 데이터가 제공되지 않았습니다."}}

- HTTP 400
- {"name": ["이 필드는 필수입니다."], "email": ["올바른 이메일을 입력해주세요."]}
+ HTTP 400
+ {"error": {
+    "code": "validation_failed",
+    "message": "이 필드는 필수입니다.",
+    "details": {"name": ["이 필드는 필수입니다."], "email": ["올바른 이메일을 입력해주세요."]}
+ }}
```

표준 에러 코드 (Phase 1 `docs/api_response_convention.md` 참조):
- `validation_failed` (400) / `authentication_required` (401) / `permission_denied` (403)
- `not_found` (404) / `method_not_allowed` (405) / `conflict` (409)
- `throttled` (429) / `internal_error` (500) / `upstream_unavailable` (502/503)

### Non-breaking — Swagger 신규 엔드포인트

| Method | URL | 응답 |
|---|---|---|
| GET | `/api/schema/` | OpenAPI 3.0 YAML (78개 path) |
| GET | `/api/schema/swagger-ui/` | Swagger UI HTML |
| GET | `/api/schema/redoc/` | ReDoc HTML |

### Non-breaking — 200 응답 본문은 그대로

목록·상세·생성 응답 형식은 변경 없음. 페이지네이션은 Phase 2의 5키 그대로.

## 5. 환경변수·설정 변경
해당 없음 (DRF/Spectacular 설정은 코드 상수만).

## 6. 마이그레이션 가이드

```bash
# 1. 풀 받기
git pull

# 2. 의존성 설치
cd drf-server && source .venv/bin/activate
uv pip install -r requirements.txt   # drf-spectacular + transitives 7개

# 3. DB 마이그레이션 변경 없음 (본 Phase의 변경에 한해)
#    (단, 별도 facilities 0008 미적용 마이그레이션이 있을 수 있음 — 그건 본 PR과 무관)

# 4. 서버 재시작
python manage.py runserver

# 5. Swagger UI 접속해 엔드포인트 확인
#    http://localhost:8000/api/schema/swagger-ui/
```

**프론트 영향 (Phase 3 회귀 점검 필수):**
- 4xx/5xx 응답을 처리하던 모든 fetch 호출처에서 `data.detail`을 직접 읽고 있다면 → `data.error?.message`로 변경 필요.
- Phase 3에서 `Auth.apiFetch`로 통일됐으므로, 한 곳만 보강해도 전 프론트 영향 자동 적용 가능.

## 7. 결정 근거 (ADR)

| 결정 | 채택안 | 검토했던 대안 | 근거 |
|---|---|---|---|
| selector 추출 범위 | **어드민 List view 3곳만 추출** | 모든 view의 ORM 호출 추출 | 가장 무겁고 중복도 높은 List view부터. 단순 `_get_user(pk)` 같은 단일 쿼리는 selector화하면 abstraction overhead. Surgical Changes. |
| selector 함수 시그니처 | **kwargs 명시 + 화이트리스트 sort** | dict 받기 / `**filters` | 호출자(view)가 query_params에서 추출해 넘기는 형태가 명확. sort는 외부 입력을 ORM에 그대로 넘기지 않기 위해 `_SORT_MAP` 화이트리스트. |
| service layer 별도 신설 | **이번 단계에선 보류** | `accounts/services/user_service.py` 신설 | 사용자 생성은 단일 모델 INSERT(serializer.create)라 service 레이어가 abstraction overhead. view에 `@transaction.atomic` 직접 데코레이터로 충분. 진정한 다중 모델 쓰기 흐름이 보이면 그때 service로. |
| 글로벌 예외 핸들러 매핑 | **`default_code` → 표준 code 명시 매핑 + status fallback** | DRF default_code 그대로 노출 | DRF의 `default_code`는 일관성이 떨어짐(예: ValidationError는 "invalid"). 표준 코드(Phase 1 결정)로 매핑 후 status 기반 폴백을 더해 어떤 예외든 표준 봉투로 변환. |
| 검증 실패 응답에 `details` 필드 | **`detail`이 단일 키일 때는 노출 안 함, 필드별 dict일 때만** | 항상 노출 / 항상 비노출 | 사용자에게 보일 message는 단일 줄, 머신 처리는 details. detail이 단순 메시지일 때 details에 똑같은 정보 중복은 노이즈. |
| Swagger 도구 선택 | **drf-spectacular** | drf-yasg | drf-spectacular가 OpenAPI 3.x를 우선 지원하고 SchemaGenerator 기반으로 정확. drf-yasg는 OpenAPI 2.x 위주로 모던 스펙 부족. |
| Swagger warn 처리 | **현재는 `--fail-on-warn` 미적용** | 모든 view에 `serializer_class` / `@extend_schema` 보강 | 20개 warn은 대부분 raw `Response()` 반환 view들의 응답 타입 추측 불가 — 점진적으로 `@extend_schema_serializer` 적용 예정. 본 PR은 schema 노출만. |
| `EquipmentAdminDetailView.put` 트랜잭션 | **반드시 적용** | 적용 안 함 | Equipment 저장 + PowerDevice 재활성화의 다중 모델 쓰기. 한 쪽 실패 시 부분 커밋이 데이터 불일치 야기. event_service의 `@transaction.atomic` 패턴 차용. |
| 트랜잭션 적용 폭 | **필요한 다중 쓰기 view에만** | 모든 POST/PUT 일괄 | 단일 모델 INSERT는 DB가 자체 트랜잭션. atomic 데코레이터 추가는 redundant. Surgical Changes. |
| `except Exception` 처리 | **socket connection_check 2곳만 구체화** | auth_views.py / dashboard/views.py의 묵음 except도 정리 | auth/dashboard의 except는 graceful degradation으로 의도된 동작 — 변경하면 회귀 위험. Phase 4 범위 좁게. |
| 로거 통일 정책 | **settings.py LOGGING dictConfig + 컨벤션 포맷 `[CATEGORY] key=value`** | 로거 모두 삭제 / 모듈별 로거 설정 분산 | 프로젝트 전체에 일관된 로깅 설계 유지. 추후 `DJANGO_LOG_LEVEL` env로 운영/개발 분기 가능. Phase 5에서 fastapi-server에도 동일 정책 적용 예정. dev_convention.md §6의 컨벤션 그대로 적용. |

## 8. 검증 방법 / 결과

### 자동 검증 (실행 완료)

```bash
cd drf-server && source .venv/bin/activate

# (1) Django check
python manage.py check
# 결과: ✅ System check identified no issues (0 silenced).

# (2) 신규 모듈 import
python -c "
import os; os.environ.setdefault('DJANGO_SECRET_KEY','test')
import django; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()
from apps.core.exceptions import standard_exception_handler
from apps.accounts.selectors.admin_users import list_admin_users
from apps.facilities.selectors.admin_devices import list_admin_gas_sensors, list_admin_power_devices
"
# 결과: ✅ 모두 import 성공

# (3) OpenAPI schema 생성
python manage.py spectacular --file /tmp/diconai_schema.yaml
ls -la /tmp/diconai_schema.yaml
grep -c "^  /" /tmp/diconai_schema.yaml
# 결과: ✅ 55KB YAML 생성, 78개 path

# (4) Swagger UI 응답
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/schema/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/schema/swagger-ui/
# 결과: ✅ 200, 200

# (5) 표준 에러 봉투 적용 확인
curl -s http://localhost:8000/api/gas-sensors/
# 결과:
# {"error":{"code":"authentication_required","message":"자격 인증 데이터가 제공되지 않았습니다."}}
# ✅ 표준 봉투 자동 변환

curl -s http://localhost:8000/api/admin/accounts/
# 결과: 동일 ✅
```

### 검증 미완 (브라우저/통합)

- [ ] **Phase 3 프론트 회귀** — 4xx/5xx 응답 형식 변경으로 `data.detail`을 직접 읽던 호출처가 있다면 깨짐. 어드민 패널 8개 페이지에서 검증 실패 케이스 한 번씩 발생시켜 에러 메시지 정상 표시 확인.
- [ ] **로그인 실패 응답** — `/api/auth/login/`에 잘못된 비밀번호 → 401 + `{error: {code: "invalid_credentials" or "authentication_required", message}}`
- [ ] **검증 오류 시 details** — 사용자 등록 시 빈 name → 400 + `error.details.name` 채워짐
- [ ] **트랜잭션 동작** — Equipment 수정 + 강제 IntegrityError → Equipment·PowerDevice 둘 다 변경 안 됨
- [ ] **Swagger UI 전체 엔드포인트 노출** — 78 path 다 보이는지, 응답 schema가 그럴듯한지

## 9. 하위 호환성 / 롤백

### Breaking 영역
- **4xx/5xx 응답 형식 변경.** 기존 클라이언트가 `data.detail`을 직접 읽고 있으면 `undefined` 반환. Phase 3에서 `Auth.apiFetch`로 통일됐으므로 한 곳만 보강(`data.error?.message`)하면 전 프론트 영향.
- 현재 프론트 코드가 에러 메시지를 노출하는 곳:
  - `admin/accounts/accounts.js`: validation 오류를 `errors.username` 같은 형태로 직접 읽음 → `{error.details}.username`으로 경로 변경 필요. Phase 3+4 결합한 검증 시점에 보강.
  - 다른 admin/* 파일은 대부분 `alert('실패했습니다.')` 같은 단순 처리라 영향 없음.

### Non-breaking 영역
- 200 응답(목록·상세·생성)은 변경 없음.
- 페이지네이션 5키 그대로.
- selector 추출은 view → DB 쿼리 결과의 변화 없음(같은 ORM 호출).

### 롤백
- `git revert <SHA>`로 충분.
- DB 변경 없음.
- 의존성: `pip uninstall drf-spectacular` 후 `requirements.txt` 되돌리기.

## 10. 후속 작업 / 참고

### 본 Phase에서 의도적으로 미룬 것
- **Swagger warn 20개 해소** — 대부분 raw `Response()` 반환 view들의 응답 타입 추측 불가. 각 view에 `@extend_schema(responses=...)` 데코레이터 점진적 적용 예정 (별도 작업).
- **dashboard/views.py의 묵음 except** — graceful degradation 의도라 회귀 위험. 별도 작업.
- **service 레이어 신설** — 사용자/센서/장비 생성에 진정한 다중 모델 쓰기 흐름이 보이면 추가.
- **fastapi-server 측 같은 표준 적용** — Phase 5에서 처리.
- **에러 응답 i18n** — 현재는 한국어 메시지 그대로. 다국어 필요 시 별도 작업.
- **drf-spectacular의 스키마 path 정규화** — `/api/admin/...`과 `/api/...` prefix가 섞여 있어 그룹핑 어색. SCHEMA_PATH_PREFIX/태그 보강은 추후.

### 관련 문서
- 응답 봉투 표준: `docs/api_response_convention.md`
- Phase 1/2/3 변경 기록: `docs/changelog/phase{1,2,3}_*.md`
- 마스터 검증 체크리스트: `docs/changelog/00_pr_verification_checklist.md`
- Swagger UI: 서버 기동 후 `/api/schema/swagger-ui/`
