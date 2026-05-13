# 변경 기록서 — Phase2 어드민 보안 핫픽스 + 페이지네이션·응답 표준화

> 작성일: 2026-05-04
> 브랜치: feature/refactor-phase2-admin-security (예정)
> 작업 종류: hotfix + refactor
> 하위 호환성: **breaking** — 어드민 패널 API 23개가 무인증 → IsSuperAdmin 필요. 슈퍼관리자 토큰 없는 호출은 401/403. 페이지네이션 응답 키는 5개로 확장(has_next 추가)이라 기존 클라이언트 호환.

---

## 1. 변경 개요

- **목적(Why):** 코드 분석에서 `apps/facilities/views/gas_sensor_admin.py`(362줄)와 `power_device_admin.py`(341줄), `facility_admin.py`(444줄), `monitoring/views/gas_data_admin.py`/`power_data_admin.py` 등 **어드민 API 23개가 `authentication_classes=[]`, `permission_classes=[]`로 설정되어 무인증 접근 가능**한 상태였음. 어드민 패널 데이터·CRUD 전체가 토큰 없이 노출된 보안 사고. 동시에 페이지네이션 응답 키가 `results`(공용 `AdminPagination`)와 `records`(수동 구현) 두 형태로 갈라져 프론트 통일을 막고 있었음.
- **결과(What):** 어드민 API 23개에 `[IsSuperAdmin]` 권한 적용. 페이지네이션 9곳을 공용 `AdminPagination`으로 통일하면서 응답 봉투에 `has_next` boolean 추가 → Phase 1에서 결정한 5키 표준 (`docs/api_response_convention.md`) 완성. 어드민 패널 페이지 진입(HTML 셸) 3개를 APIView+render() 안티패턴에서 표준 `TemplateView`로 전환해 권한 설정 위치 모호성 제거.
- **영향 범위(Where):** drf-server 백엔드만. FastAPI·프론트엔드 영향 없음(프론트는 응답 키 호환 유지 — 신규 키만 추가됨).

## 2. Before / After 비교

| 구분 | Before | After |
|---|---|---|
| 어드민 API 권한 | `authentication_classes=[]`, `permission_classes=[]` (무인증) | `permission_classes=[IsSuperAdmin]` (JWT + 슈퍼관리자) |
| 페이지네이션 응답 키 | 공용 `{results,total,page,page_size}` 또는 수동 `{records|results,total,page,page_size}` 혼재 | 모든 어드민 목록이 `{results,total,page,page_size,has_next}` (5키) |
| 어드민 패널 페이지 view | `APIView` + `render()` 호출 (권한 위치 모호 → 빈 리스트로 노출) | `TemplateView` (HTML 셸만 반환, 권한 검사는 API 호출 시점) |
| 수동 페이지 계산 | `try: page = int(request.query_params.get("page",1))` 9곳 중복 | `paginator.paginate_queryset(qs, request)` 1줄 |
| `gas_data_admin.py` `GasDataAdminListView` (예시) | 수동 슬라이싱 + `Response({...})` 직접 조립 | `AdminPagination` + `paginator.get_paginated_response()` |

### 코드 차이 예시

```python
# Before (gas_data_admin.py)
authentication_classes = []
permission_classes = []

def get(self, request):
    qs = _build_queryset(request.query_params)
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = max(1, min(100, int(request.query_params.get("page_size", 20))))
    except (ValueError, TypeError):
        page, page_size = 1, 20
    total = qs.count()
    items = qs[(page - 1) * page_size : page * page_size]
    return Response({"total": total, "page": page, "page_size": page_size,
                     "results": [_serialize_row(o) for o in items]})

# After
permission_classes = [IsSuperAdmin]

def get(self, request):
    qs = _build_queryset(request.query_params)
    paginator = AdminPagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response([_serialize_row(o) for o in page])
```

## 3. 변경 파일 목록

### 신규
해당 없음.

### 수정
| 파일 | 변경 요약 |
|---|---|
| `drf-server/apps/core/pagination.py` | `AdminPagination.get_paginated_response`에 `has_next` 키 추가 |
| `drf-server/apps/facilities/views/gas_sensor_admin.py` | PageView → TemplateView, API 9개 `IsSuperAdmin` 적용, List view 페이지네이션을 `AdminPagination`으로 |
| `drf-server/apps/facilities/views/power_device_admin.py` | PageView → TemplateView, API 8개 `IsSuperAdmin` 적용, List view 페이지네이션 통일 |
| `drf-server/apps/facilities/views/facility_admin.py` | PageView → TemplateView, API 12개 `IsSuperAdmin` 명시, Facility/Equipment/PowerDevice List 3곳 페이지네이션 통일 |
| `drf-server/apps/monitoring/views/gas_data_admin.py` | API 3개 `IsSuperAdmin` 적용, List view 페이지네이션 통일 |
| `drf-server/apps/monitoring/views/power_data_admin.py` | API 3개 `IsSuperAdmin` 적용, List view 페이지네이션 통일 |
| `drf-server/apps/monitoring/views/gas_data.py` | 의도적 무인증 ingest 엔드포인트임을 주석으로 명시 (Phase 5 추가 보호 예정) |
| `drf-server/apps/monitoring/views/power_data.py` | 의도적 무인증 ingest 엔드포인트(3개) 주석 명시 |

### 삭제
해당 없음.

## 4. API / 응답 / 인터페이스 변경

### 권한 변경 (Breaking)

| 엔드포인트 | Before | After |
|---|---|---|
| `/api/admin/gas-sensors/...` (9개) | 무인증 | JWT + IsSuperAdmin |
| `/api/admin/power-devices/...` (8개) | 무인증 | JWT + IsSuperAdmin |
| `/api/admin/facilities/...`, `/equipments/...`, `/power-devices/...` (12개) | DEFAULT 인증(IsAuthenticated)만 | JWT + IsSuperAdmin |
| `/api/admin/gas-data/...` (3개) | 무인증 | JWT + IsSuperAdmin |
| `/api/admin/power-data/...` (3개) | 무인증 | JWT + IsSuperAdmin |
| `/api/monitoring/gas/`, `/api/monitoring/power/event/`, `/data/`, `/thresholds/` | 무인증 (의도) | 유지 (서버-서버 ingest, Phase 5에서 별도 보호) |

### 응답 봉투 변경 (Non-breaking — 기존 키 유지, `has_next`만 추가)

```diff
  {
    "results": [...],
    "total": 137,
    "page": 1,
-   "page_size": 20
+   "page_size": 20,
+   "has_next": true
  }
```

수동 페이지네이션 응답 키 `records`를 사용하는 곳은 **없었음** (분석 결과 `gas_sensor_admin.py:204-211`, `power_device_admin.py:182-189` 등 모두 이미 `results`였음). 따라서 키 이름 변경에 따른 프론트 영향 없음.

## 5. 환경변수·설정 변경
해당 없음.

## 6. 마이그레이션 가이드

```bash
# 1. 풀 받기
git pull

# 2. DB 마이그레이션 변경 없음

# 3. 의존성 변경 없음

# 4. 서버 재시작
cd drf-server && python manage.py runserver

# 5. 어드민 패널 동작 확인
#    - 슈퍼관리자 토큰으로 로그인 → /admin-panel/gas-sensors/, /facility/, /power_system/ 정상
#    - 일반 사용자 토큰 → 403 (어드민 진입 차단됨)
#    - 토큰 없음 → JS의 Auth.apiFetch가 401 → /accounts/login/ 자동 리다이렉트
```

**기존 동작 영향:**
- 슈퍼관리자가 아닌 사용자 계정으로 어드민 패널 API를 호출하던 코드/스크립트가 있다면 403을 받게 됨. 슈퍼관리자 권한 부여 또는 권한 정책 재검토 필요.
- 무인증으로 노출되어 있던 API를 외부 도구(Postman 등)에서 호출하던 사용 사례가 있다면 슈퍼관리자 토큰 부착 필수.

## 7. 결정 근거 (ADR)

| 결정 | 채택안 | 검토했던 대안 | 근거 |
|---|---|---|---|
| 어드민 API 권한 클래스 | `[IsSuperAdmin]` 단일 | `[IsAuthenticated, IsSuperAdmin]`, `[IsSuperAdminOrFacilityAdmin]` | `IsSuperAdmin`이 내부적으로 `request.user.is_authenticated`를 검사하므로 `IsAuthenticated` 중복 불요. 어드민 패널은 슈퍼관리자만 사용하는 화면이라 `OrFacilityAdmin`은 권한 과대. 기존 모범인 `accounts/admin_views.py`도 `[IsSuperAdmin]` 단일 사용. |
| 어드민 패널 페이지 view 패턴 | `TemplateView` | `LoginRequiredMixin + TemplateView`, `APIView + IsSuperAdmin` 유지 | 현 시스템은 JWT(localStorage) 기반이라 페이지 GET 요청에는 토큰이 안 붙음. `LoginRequiredMixin`은 Django 세션 인증을 요구하므로 부적합. `APIView + IsSuperAdmin`은 페이지 GET이 401로 막혀 화면 진입 자체가 불가. 현실적 정답은 **HTML 셸은 무인증 노출 + JS가 페이지 로드 후 API 호출 시 JWT로 검증**. `TemplateView`가 이 의도에 가장 부합. |
| 서버-서버 ingest view 보호 | **이번 단계는 보존, Phase 5에서 처리** | 즉시 IP 화이트리스트 또는 서비스 토큰 도입 | fastapi 측 호출 코드도 동시에 변경해야 하는 양면 작업이라 Phase 5(fastapi 정리)에서 함께 다루는 게 안전. 이번에는 의도적 무인증임을 코드 주석으로 명시해 보안 감사 시 오해 방지. |
| 수동 페이지네이션 9곳 일괄 통일 | **AdminPagination로 전부 교체** | 일부만 통일 / 개별 수정 | 응답 키 표준(Phase 1 결정)을 만족시키려면 어차피 모두 손대야 함. `AdminPagination`은 이미 검증된 코드(`accounts/admin_views.py`가 사용 중)이고 한 줄로 끝나 코드 양 줄어듦. |
| `has_next` 추가 | **boolean 키 추가** | DRF 기본 `next/previous` URL 사용 | 페이지 번호 기반 UI(SPA 아님)에서 URL 형식보다 boolean이 단순. 프론트 마지막 페이지 비활성화 UI에 직접 사용 가능. |
| 페이지네이션 안 된 List/Detail (예: `FacilitySelectView`) | 그대로 유지 | 강제로 페이지네이션 적용 | 이들은 드롭다운 옵션·전체 옵션 반환용으로 100건 미만이라 페이지네이션 부적합. |

## 8. 검증 방법 / 결과

### 자동 검증 (실행 완료)

```bash
cd drf-server && source .venv/bin/activate

# (1) Django check
python manage.py check
# 결과: ✅ System check identified no issues (0 silenced).

# (2) 모든 어드민 view에 IsSuperAdmin 적용 확인 (Python 인스펙트)
python -c "
... (검증 스크립트 — phase2 verification 통과)
"
# 결과:
# AdminPagination 5 keys: OK
# gas_sensor_admin 9 views protected: OK
# power_device_admin 8 views protected: OK
# gas_data_admin 3 views protected: OK
# power_data_admin 3 views protected: OK
# 3 PageViews are TemplateView: OK
# === Phase 2 verification PASSED ===

# (3) 잔존 무인증 view 검색 (의도적 ingest 1건만 남아야 함)
grep -rn "authentication_classes = \[\]\|permission_classes = \[\]" drf-server/apps/
# 결과: gas_data.py만 잔존 (의도적, 주석으로 명시됨)
```

### 검증 미완 (실제 서버 기동 후 확인 필요)

- [ ] 슈퍼관리자 토큰으로 `/api/admin/gas-sensors/` 호출 → 200 + `{results,...,has_next}` 응답
- [ ] 토큰 없이 호출 → 401
- [ ] 일반 사용자(worker) 토큰으로 호출 → 403
- [ ] 어드민 패널 페이지 14개 (`/admin-panel/...`) 정상 렌더링
- [ ] 페이지네이션 UI 마지막 페이지에서 `has_next=false` 처리 확인 (Phase 3에서 프론트 활용)

## 9. 하위 호환성 / 롤백

### Breaking 영역
- **어드민 API 23개**가 무인증 → 인증 필수로 전환됨. 기존에 토큰 없이 호출하던 클라이언트는 401/403 받게 됨.
- 일반 작업자 권한으로 호출하던 사용 사례가 있었다면 403 (슈퍼관리자만 허용).

### Non-breaking 영역
- 페이지네이션 응답에 `has_next`가 추가되었으나 기존 4개 키는 그대로 유지 → 기존 프론트 코드 영향 없음.
- 어드민 페이지 HTML 진입은 변경 없음 — TemplateView로 전환했지만 동일 템플릿·동일 context 노출.

### 롤백
- `git revert <SHA>`로 충분. DB 변경 없음, 의존성 변경 없음.
- 단, 이 PR을 revert하면 보안 노출 상태로 돌아감 — 신중히.

## 10. 후속 작업 / 참고

### 본 Phase에서 의도적으로 미룬 것
- **서버-서버 ingest view 보호** (`monitoring/views/gas_data.py`, `power_data.py`, `positioning/views/position_views.py`) — fastapi 측 호출 코드와 동시 작업이라 **Phase 5**에서 함께. 보호 방식은 (a) 서비스 토큰 헤더 검증 또는 (b) 미들웨어 IP 화이트리스트 검토 예정.
- **`apps/accounts/views/admin_views.py`의 미사용 `AccountsAdminPageView`/`OrganizationsAdminPageView`** (APIView + render 패턴) — `admin_panel_urls.py`가 자체 TemplateView를 정의해 사용 중이라 이 클래스들은 dead code. 정리는 **Phase 4** (레이어 정리)에서.
- **DRF 전역 예외 핸들러로 4xx/5xx 응답을 `{error: {code, message}}` 표준으로 변환** — **Phase 4**.
- **view에 ORM 직접 호출 추출 → `selectors/`/`services/`** — **Phase 4**.
- **`gas_sensor_admin.py:114-121`의 `except Exception: ok=False` 묵음 패턴** — Phase 4 방어적 예외 처리.

### 관련 문서
- 응답 봉투 표준: `docs/api_response_convention.md`
- Phase 1 변경 기록: `docs/changelog/phase1_config_centralization.md`
- 마스터 플랜: `~/.claude/plans/streamed-sparking-dongarra.md`
- 변경기록 프롬프트: `skill/system_instruction_changelog.md`
