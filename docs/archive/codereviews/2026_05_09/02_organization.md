# 02. 조직 관리 (Users · Departments · Members)

## 1. 범위

### 1.1 API 엔드포인트
| URL | 메서드 | 뷰 | 권한 |
|---|---|---|---|
| `/api/admin/accounts/` | GET, POST | AccountsAdminListView | IsSuperAdmin |
| `/api/admin/accounts/<id>/` | GET, PATCH, DELETE | AccountsAdminDetailView | IsSuperAdmin |
| `/api/admin/accounts/<id>/<action>/` | POST | AccountsAdminLockView | IsSuperAdmin |
| `/api/admin/organizations/tree/` | GET | OrgTreeView | IsSuperAdmin |
| `/api/admin/departments/` | POST | DeptListCreateView | IsSuperAdmin |
| `/api/admin/departments/<id>/` | GET, PATCH, DELETE | DeptDetailView | IsSuperAdmin |
| `/api/admin/departments/<pk>/members/` | GET | DeptMemberListView | IsSuperAdmin |
| `/api/admin/departments/<id>/members/add/` | POST | DeptMemberAddView | IsSuperAdmin |
| `/api/admin/departments/<pk>/members/move/` | POST | DeptMemberMoveView | IsSuperAdmin |
| `/api/admin/departments/<id>/members/remove/` | POST | DeptMemberRemoveView | IsSuperAdmin |
| `/api/admin/departments/<id>/members/assign-leader/` | POST | DeptLeaderAssignView | IsSuperAdmin |

### 1.2 백엔드 파일
- [drf-server/apps/accounts/views/admin_views.py](../../../../drf-server/apps/accounts/views/admin_views.py) — 276줄, 사용자 CRUD + 잠금
- [drf-server/apps/accounts/views/org_views.py](../../../../drf-server/apps/accounts/views/org_views.py) — **629줄, 분리 시급**
- [drf-server/apps/accounts/selectors/admin_users.py](../../../../drf-server/apps/accounts/selectors/admin_users.py)
- [drf-server/apps/accounts/serializers/admin_serializers.py](../../../../drf-server/apps/accounts/serializers/admin_serializers.py)
- [drf-server/apps/accounts/serializers/org_serializers.py](../../../../drf-server/apps/accounts/serializers/org_serializers.py)
- [drf-server/apps/core/models/system_log.py](../../../../drf-server/apps/core/models/system_log.py) — 변경 이력 감사 로그

### 1.3 프론트엔드 파일
- [drf-server/static/js/admin/accounts/accounts.js](../../../../drf-server/static/js/admin/accounts/accounts.js)
- [drf-server/static/js/admin/organizations/organizations.js](../../../../drf-server/static/js/admin/organizations/organizations.js)
- [drf-server/templates/admin_panel/accounts/](../../../../drf-server/templates/admin_panel/accounts/)
- [drf-server/templates/admin_panel/organizations/](../../../../drf-server/templates/admin_panel/organizations/)

## 2. 기능 흐름

### 2.1 사용자 목록 조회·필터
```
1. accounts.js init() → fetchList() 호출
2. GET /api/admin/accounts/?name=..&department=..&user_type=..&sort=name_asc&page=1
3. AccountsAdminListView.get:
   ├─ list_admin_users(...) selector — 필터링·정렬된 queryset 반환
   ├─ AdminPagination paginate
   └─ AccountsAdminListSerializer 직렬화
4. JS: 응답을 받아 _renderTable() — badge 색상·상태 라벨 매핑
```

### 2.2 사용자 등록/수정/비활성화
```
1. JS 모달 → POST /api/admin/accounts/ (또는 PATCH .../<id>/)
2. AccountsAdminListView.post @transaction.atomic:
   ├─ AccountsAdminCreateSerializer.is_valid()
   ├─ serializer.save() (비밀번호 해싱은 serializer 내부)
   └─ 201 응답
3. DELETE → user.deactivate() (소프트 삭제, is_active=False)
   ※ SystemLog 미기록 (조직 작업과 달리 감사 로그 누락)
```

### 2.3 계정 잠금/해제
```
1. JS: POST /api/admin/accounts/<id>/lock/ (또는 .../unlock/)
2. AccountsAdminLockView.post(action):
   ├─ action=="lock"  → account_locked_until = now + 36500일 (100년)
   ├─ action=="unlock" → account_locked_until=None, failed_login_count=0
   └─ 그 외 → 400
```

### 2.4 조직도/구성원
```
1. organizations.js loadTree()
   └─ GET /api/admin/organizations/tree/ → 회사·부서 트리 + 미소속 인원 수
2. 부서 클릭 → GET /api/admin/departments/<id>/members/?q=..&page=..
3. 구성원 추가/이동/제외 → 각각 POST .../add, .../move, .../remove
4. 모든 변경: SystemLog에 ActionType.MEMBER_*로 감사 로그 기록
```

## 3. 백엔드 소견

### 3.1 일반 코드 리뷰
- **[중] 매직스트링 URL action**
  [admin_views.py:248-273](../../../../drf-server/apps/accounts/views/admin_views.py#L248-L273) `AccountsAdminLockView`가 URL의 `<action>`(lock/unlock)으로 분기. RESTful 관점에선 별도 엔드포인트(`/lock/`, `/unlock/`) 두 개로 분리가 명확. 또는 PATCH `.../<id>/` body로 처리.
- **[중] "100년 뒤"로 무기한 잠금 표현**
  [admin_views.py:258](../../../../drf-server/apps/accounts/views/admin_views.py#L258) `now + 36500일`로 무기한을 흉내. 의미 모호 + 100년 후 자동 해제 위험. `is_locked_manually=True` boolean이나 `account_locked_until=None + locked_by_admin=True` 같은 명시 모델 권장.
- **[상] org_views.py 629줄 모놀리식**
  8개 view 클래스가 한 파일 + 모듈 레벨 `_log()`. 도메인별 분리 필요: `org_views/tree.py`, `org_views/department.py`, `org_views/members.py`.
- **[상] 부분 실패 시 일관성 깨짐 (트랜잭션 부재)**
  [org_views.py:351-397](../../../../drf-server/apps/accounts/views/org_views.py#L351-L397) `DeptMemberAddView.post`의 for loop은 `@transaction.atomic` 미적용. 중간에 예외 발생 시 일부 사용자만 부서 변경 + 일부 SystemLog만 기록 → 부분 실패. `move`, `remove`도 동일. **모든 변경 view에 `@transaction.atomic` 추가 시급**.
- **[중] DeptMemberRemoveView N+1 쿼리**
  [org_views.py:538-549](../../../../drf-server/apps/accounts/views/org_views.py#L538-L549) `for uid in user_ids: User.objects.get(pk=uid)` — 사용자별로 매번 쿼리. `User.objects.filter(pk__in=user_ids)` 한 번에 조회 후 dict 매핑.
- **[중] 중복 로직: add/move의 분기 본문이 거의 동일**
  [DeptMemberAddView.post:368-386](../../../../drf-server/apps/accounts/views/org_views.py#L368-L386)와 [DeptMemberMoveView.post:456-471](../../../../drf-server/apps/accounts/views/org_views.py#L456-L471)의 `keep_previous` 처리 본체가 동일. `services/membership.py::set_primary_membership(user, dept, keep_previous)` 추출.
- **[중] _log 헬퍼 + IP 추출 중복**
  [org_views.py:33-51](../../../../drf-server/apps/accounts/views/org_views.py#L33-L51)의 IP 추출이 [auth_views._get_client_ip](../../../../drf-server/apps/accounts/views/auth_views.py#L34)와 중복. `apps/core/utils/request_ip.py`로 단일화. SystemLog 기록도 `services/system_log.py`로 추출 권장.

### 3.2 아키텍처/레이어
- **[상] selectors/services 부재**
  - `selectors/admin_users.py`만 존재. 부서·구성원·트리 조회는 view에서 직접 ORM. `selectors/organizations.py` 추가 권장.
  - `services/__init__.py` 빈 패키지. 사용자 등록·잠금·구성원 조작 로직은 모두 services로 이전 가능.
- **[중] view 책임 과다**
  특히 org_views의 각 view가: 권한 체크 + 입력 검증 + ORM 조작 + 로그 기록 + 응답 직렬화를 모두 수행. service 추출 시 view는 30~40줄로 줄어듦.
- **[하] _get_dept 메서드 중복**
  [admin_views.py:132-140](../../../../drf-server/apps/accounts/views/admin_views.py#L132-L140), [org_views.py:145-151,225-229](../../../../drf-server/apps/accounts/views/org_views.py#L145-L151) 등 `try-except DoesNotExist → None` 패턴이 5번 반복. `selectors/...get_or_404()` 헬퍼 또는 DRF `get_object_or_404` 사용.

### 3.3 보안 관점 (요약)
- **[중] PATCH/DELETE에 SystemLog 기록 누락 (사용자 도메인)**
  org_views는 모든 변경을 SystemLog로 감사 기록. 반면 [admin_views.py](../../../../drf-server/apps/accounts/views/admin_views.py)의 사용자 PATCH/DELETE/lock/unlock은 SystemLog 미사용 — 누가 누구 계정을 잠갔는지 추적 불가. 일관성 위해 사용자 도메인도 SystemLog 적용 시급.
- **[하] 사용자 잠금 무한 카운터 / 자가 잠금 회피**
  본인 계정 비활성화는 [admin_views.py:205](../../../../drf-server/apps/accounts/views/admin_views.py#L205)에서 차단. 그러나 본인 계정 lock은 차단되지 않음 → super_admin이 본인을 잠그면 모든 super_admin이 잠긴 경우 잠금 해제 불가 (단일 super_admin 환경 가정 시 위험). `lock` 본인 차단 추가 권장.
- **[하] _log()의 raw IP 신뢰**
  X-Forwarded-For 우선 — 01의 A6과 동일 이슈, 한 번에 해결.

## 4. 프론트엔드(JS/HTML) 소견

### 4.1 백엔드 contract 정합성
- **[하] AccountsAdmin·Org 두 페이지 모듈이 매우 유사한 fetch 패턴**
  organizations.js는 [`_api(method, url, body)`](../../../../drf-server/static/js/admin/organizations/organizations.js#L22) 헬퍼를 둠. accounts.js는 직접 `Auth.apiFetch` 호출. **공유 헬퍼 부재**로 같은 패턴이 페이지마다 살짝 다른 구현. `shared/api-helper.js::api(method, url, body)` 단일화.

### 4.2 클라이언트 권한 체크의 한계
- **[중] _showAccessDenied가 클라이언트만 차단**
  [accounts.js:42-65](../../../../drf-server/static/js/admin/accounts/accounts.js#L42-L65)는 권한 없을 시 모달. 그러나 페이지 자체는 누구나 접근 가능 + 권한 체크는 API 레벨에서 401/403로 이뤄짐. 클라이언트 모달은 UX일 뿐 보안 경계 아님 — 명시적 주석 추가 권장 (초보자가 "이게 보안 처리"로 오해 가능).

### 4.3 UX/안정성
- **[중] 일괄 작업 진행률·실패 처리 미흡**
  부서 이동·제외는 user_ids 배열을 한 요청으로 받음. 100명 이동 중 1명에서 실패하면 응답은 200 OK + `{"ok":true,"moved":N}` (실패는 묵살). 부분 실패 시 각 사용자별 상태 반환 권장 (`{success:[..], failed:[{id, reason}, ..]}`).
- **[하] DOM 인라인 SVG 반복**
  `_renderTree`/`_makeDeptItem`에 SVG 마크업이 인라인 — 대량 렌더링 시 비효율. SVG sprite + `<use>` 패턴으로 분리 권장 (작은 개선이지만 부서·사용자 수가 많아질수록 효과).

## 5. 개선 제안

### B1. org_views.py 분리 [상 · 중]
- **왜 필요?**: 629줄 단일 파일은 가독성·머지 충돌·테스트 격리 모두 어렵게 만든다.
- **장점**: 도메인별 격리 / git diff 명확 / 테스트 파일과 1:1 대응.
- **단점**: import 경로 1회 변경 / PR 리뷰 시 "파일 이동 vs 내용 변경" 구분 필요.
- **변경 위치**: `views/org_views/{tree.py, department.py, members.py}` 분리, `views/org_views/__init__.py`에서 re-export.

### B2. 트랜잭션 일관성 [상 · 소]
- **왜 필요?**: 구성원 추가·이동·제외는 N건의 ORM 변경 + N건의 SystemLog. 중간에 예외 발생 시 부분 적용 → 데이터 불일치.
- **장점**: 부분 실패 시 자동 롤백 / 데이터 정합성 보장.
- **단점**: 트랜잭션 길이가 길어지면 락 경합 가능 — 현재 부서/구성원 조작 빈도는 낮아 사실상 영향 없음.
- **변경 위치**: 모든 변경 view post 메서드에 `@transaction.atomic` 데코레이터 추가.

### B3. 사용자 도메인에도 SystemLog 적용 [상 · 중]
- **왜 필요?**: 누가 누구 계정을 잠그고 비활성화했는지 추적 불가 → 감사·컴플라이언스 미충족.
- **장점**: 통일된 감사 트레일 / 운영 사고 시 원인 추적 가능.
- **단점**: SystemLog 테이블 증가 / `ActionType` enum 4종 추가 필요.
- **변경 위치**: [admin_views.py](../../../../drf-server/apps/accounts/views/admin_views.py) PATCH/DELETE/lock/unlock 후처리에 _log() 호출 추가. 단, _log를 [services/system_log.py](../../../../drf-server/apps/accounts/services/) 헬퍼로 먼저 추출 (B6과 함께).

### B4. account_locked_until 100년 트릭 제거 [중 · 중]
- **왜 필요?**: 잠금 의도("관리자 수동 무기한")가 코드에 표현되지 않음. 코드 읽는 사람이 36500의 의미를 알아야 함.
- **장점**: 의도 명확 / 100년 후 자동 해제 버그 방지.
- **단점**: 마이그레이션 필요 + 로그인 검사 로직(`is_locked` property) 동시 수정.
- **변경 위치**: User 모델에 `is_locked_manually=BooleanField` 추가, [accounts/models/user.py의 is_locked property] 수정, AccountsAdminLockView 변경.

### B5. selectors/services 레이어 정착 [중 · 대]
- **왜 필요?**: 컨벤션 위반 + 같은 쿼리·로직이 여러 view에 반복.
- **장점**: 테스트 용이 / 재사용 / view 30줄 이내로 축소.
- **단점**: 작업량 큼 (8개 view + 새 파일 3~4개).
- **변경 위치**: 신규 [selectors/organizations.py](../../../../drf-server/apps/accounts/selectors/), [services/membership.py](../../../../drf-server/apps/accounts/services/), [services/account_admin.py](../../../../drf-server/apps/accounts/services/).

### B6. _log/IP 추출 헬퍼 단일화 [중 · 소]
- **왜 필요?**: org_views의 _log()와 auth_views의 _get_client_ip()가 사실상 동일. 추후 변경 시 두 곳 수정 필요.
- **장점**: 한 곳 변경 / 다른 도메인(alerts, monitoring)에서도 재사용.
- **단점**: 없음 (단순 추출).
- **변경 위치**: [apps/core/utils/request_ip.py](../../../../drf-server/apps/core/), [apps/core/services/system_log.py](../../../../drf-server/apps/core/).

### B7. 일괄 작업 부분 실패 응답 표준화 [중 · 중]
- **왜 필요?**: 100명 일괄 이동 중 일부 실패해도 200 OK라 운영자가 인지 불가.
- **장점**: 부분 실패 가시성 / UI에서 실패 행 강조 가능.
- **단점**: 응답 스키마 변경 (프론트 연동 갱신 필요).
- **변경 위치**: 응답 표준 `{success:[ids], failed:[{id, reason}], total}`. 트랜잭션 실패 시는 전체 롤백(B2)과 충돌 — savepoint 패턴 필요.

### B8. 본인 계정 lock 차단 [하 · 소]
- **왜 필요?**: super_admin 1명 환경에서 자기 자신을 잠그면 시스템 락아웃 가능.
- **장점**: 운영 사고 방지.
- **단점**: 없음.
- **변경 위치**: [admin_views.py:248](../../../../drf-server/apps/accounts/views/admin_views.py#L248) `if action=='lock' and user.pk == request.user.pk: return 400`.

### B9. action을 별도 엔드포인트로 분리 [하 · 소]
- **왜 필요?**: `/<id>/lock/`, `/<id>/unlock/` 두 개가 RESTful + drf-spectacular 스키마 명확.
- **장점**: OpenAPI 문서가 명확 / URL routing 간단.
- **단점**: 기존 클라이언트 호출 변경 필요(JS 1군데).
- **변경 위치**: admin_urls.py path 추가, AccountsAdminLockView를 `LockView`/`UnlockView`로 분리.

### B10. shared API 헬퍼 [하 · 소]
- **왜 필요?**: `_api()` 패턴이 페이지마다 살짝 다른 구현으로 반복.
- **장점**: JS 페이지 간 일관성.
- **단점**: shared/auth.js와 책임 경계 명확화 필요.
- **변경 위치**: [shared/api-helper.js](../../../../drf-server/static/js/shared/) 신규.

## 6. 구현 추천 순서

### 1단계 — 데이터 정합성·감사 (즉시) ⚡
- **B2** 트랜잭션: 한 줄 추가로 부분 실패 회복
- **B3** 사용자 도메인 SystemLog: 운영 추적성 즉시 향상
- **B6** _log/IP 헬퍼 단일화 (B3과 함께)
- **이유**: 데이터 손상·감사 누락은 사고 발생 시 가장 큰 비용. 코드 변경 작은 데 비해 효과 큼.

### 2단계 — 파일 분리·아키텍처 정리 (다음 sprint) 🏗
- **B1** org_views.py 분리 (629→3파일)
- **B5** selectors/services 정착 (시간 들지만 컨벤션 정합)
- **이유**: B1·B5는 함께 진행하면 중복 작업 없음. B2·B3 적용 후 안정된 환경에서 리팩토링.

### 3단계 — 도메인 모델 정리 (여유 시) 🧱
- **B4** 100년 트릭 제거 (마이그레이션 필요)
- **B8** 본인 lock 차단

### 4단계 — UX·정합성 (여유 시) ✨
- **B7** 일괄 작업 부분 실패 응답
- **B9** action 분리
- **B10** JS shared 헬퍼

### ⚠️ 주의사항 (초보자용)
- **B2 트랜잭션 추가는 반드시 테스트 후 머지**: `@transaction.atomic`을 부적절하게 적용하면 중첩 트랜잭션이나 락 대기 문제 발생 가능. 단위 테스트로 정상 케이스만 통과하면 안 되고, 의도적으로 중간 실패 시나리오를 만들어 롤백 동작 확인.
- **B4는 마이그레이션이 위험**: 기존 잠금된 계정을 새 필드로 옮기는 데이터 마이그레이션 필요. 운영 DB 백업 + 점검 시간 필수.
- **B5는 큰 작업**: PR을 도메인별(사용자/부서/구성원)로 쪼개서 머지 권장. 한 번에 하면 리뷰 어렵고 회귀 위험.
