# 03. 대시보드·안전 (Dashboard · Safety · VR Training)

## 1. 범위

### 1.1 API/페이지 엔드포인트
| URL | 종류 | 메서드 | 뷰 | 권한 |
|---|---|---|---|---|
| `/dashboard/` | 페이지 | GET | main_dashboard | (서버 무인증) |
| `/dashboard/profile/` | 페이지 | GET | my_profile_page | (서버 무인증) |
| `/dashboard/safety/checklist/` | 페이지 | GET | safety_checklist_page | (서버 무인증) |
| `/dashboard/safety/history/` | 페이지 | GET | safety_history_page | (서버 무인증) |
| `/dashboard/safety/vr/` | 페이지 | GET | safety_vr_page | (서버 무인증) |
| `/dashboard/monitoring/realtime/` | 페이지 | GET | monitoring_realtime_page | (서버 무인증) |
| `/dashboard/monitoring/{gas,power,workers,events}/` | 페이지 | GET | 4개 함수 뷰 | (서버 무인증) |
| `/dashboard/monitoring/events/<id>/` | 페이지 | GET | monitoring_event_detail_page | (서버 무인증) |
| `/dashboard/api/menu/` | API | GET | MenuView | IsAuthenticated |
| `/dashboard/api/vr-progress/` | API | GET, POST | VRProgressView | **AllowAny** |
| `/dashboard/api/safety-status/` | API | GET, POST | MySafetyStatusView | **AllowAny** |
| `/dashboard/api/safety-history/` | API | GET | SafetyHistoryAPIView | IsAuthenticated |
| `/dashboard/api/workers-list/` | API | GET | WorkerListAPIView | IsAuthenticated (관리자만 통과) |
| `/dashboard/api/refresh/` | API | GET | DashboardRefreshView | IsAuthenticated |

### 1.2 백엔드 파일
- [drf-server/apps/dashboard/views.py](../../../drf-server/apps/dashboard/views.py) — **451줄, 모놀리식** (페이지 뷰 11개 + API 6개)
- [drf-server/apps/dashboard/menu.py](../../../drf-server/apps/dashboard/menu.py) — 권한별 메뉴 트리 정의
- [drf-server/apps/dashboard/urls.py](../../../drf-server/apps/dashboard/urls.py)
- [drf-server/apps/dashboard/signals.py](../../../drf-server/apps/dashboard/signals.py) — 시그널 (확인 필요)
- [drf-server/apps/dashboard/models/](../../../drf-server/apps/dashboard/models/) — Menu, RoleMenuVisibility 등
- [drf-server/apps/safety/](../../../drf-server/apps/safety/) — selectors/services/views/serializers 풀 구조 (체크리스트·VR 세션)
- [drf-server/apps/training/](../../../drf-server/apps/training/) — VR 콘텐츠 (단순 모델)

### 1.3 프론트엔드 파일
- 대시보드 메인:
  - [drf-server/static/js/dashboard/app.js](../../../drf-server/static/js/dashboard/app.js) — 진입점·패널 초기화
  - [drf-server/static/js/dashboard/charts.js](../../../drf-server/static/js/dashboard/charts.js)
  - [drf-server/static/js/dashboard/websocket.js](../../../drf-server/static/js/dashboard/websocket.js) — `/ws/sensors/` 통합 스트림 수신
  - [drf-server/static/js/dashboard/panels/](../../../drf-server/static/js/dashboard/panels/) — event-panel, map-panel, scenario-panel, worker-panel
- 서브 페이지(SNB):
  - [drf-server/static/js/detail/safety_checklist.js](../../../drf-server/static/js/detail/safety_checklist.js)
  - [drf-server/static/js/detail/safety_history.js](../../../drf-server/static/js/detail/safety_history.js)
  - [drf-server/static/js/detail/safety_vr.js](../../../drf-server/static/js/detail/safety_vr.js)
  - [drf-server/static/js/detail/my_profile.js](../../../drf-server/static/js/detail/my_profile.js)
- 템플릿:
  - [drf-server/templates/dashboard/main.html](../../../drf-server/templates/dashboard/main.html)
  - [drf-server/templates/dashboard/panels/](../../../drf-server/templates/dashboard/panels/) — 6개 패널 템플릿
  - [drf-server/templates/snb_details/](../../../drf-server/templates/snb_details/) — 9개 서브 페이지

## 2. 기능 흐름

### 2.1 대시보드 진입 → 권한별 메뉴 노출
```
1. 사용자가 /dashboard/ 진입 (HTML 렌더, 인증 체크 없음)
2. main.html이 dashboard/app.js 로드
3. app.js → Auth.getMe() → /api/auth/me/ 호출
   ├─ 401 → /accounts/login/ 리다이렉트
   └─ 200 → menu_tree·admin_url 받아 사이드바 렌더
4. dashboard/websocket.js → WSClient로 /ws/sensors/ 연결
5. 각 panel(.js)이 자기 영역 렌더 + WS 메시지 구독
```

### 2.2 안전확인 (체크리스트 + VR)
```
1. /dashboard/api/safety-status/ GET → 오늘 완료 여부 (세션 기반)
2. /dashboard/safety/checklist/ 페이지 → safety_checklist.js
   ├─ 항목 체크 후 "확인 완료" 클릭
   └─ POST /dashboard/api/safety-status/ {key:"checklist"} → 세션에 오늘 날짜 저장
3. /dashboard/safety/vr/ 페이지 → safety_vr.js
   ├─ VR 영상 시청 진도 → POST /api/vr-progress/ {position}
   └─ 완료 시 POST /api/safety-status/ {key:"vr"}
4. /dashboard/safety/history/ → SafetyHistoryAPIView
   └─ apps.safety.SafetyStatus 모델에서 월별 이력 조회 (DB 영속)
```

> ⚠️ **세션과 DB의 이중 진실 원천 (truth source) 문제**: VR/체크리스트 "오늘 완료" 상태는 세션에, 월별 히스토리는 `SafetyStatus` 모델에. POST 시 **세션만 갱신하고 SafetyStatus를 update하지 않으면** 히스토리에 안 남는 가능성. 코드상 POST 핸들러가 세션만 set하므로 별도 시그널이나 동기화 필요.

### 2.3 작업자 목록 (관리자 전용)
```
1. monitoring_workers 페이지 → monitoring_workers.js
2. GET /dashboard/api/workers-list/?department_id=X&name=Y
3. WorkerListAPIView:
   ├─ user_type 체크 (facility_admin/super_admin 아니면 403)
   ├─ facility_admin은 자기 공장만, super_admin은 전체
   ├─ Exists(WorkerPosition where measured_at__date=today)로 is_present 계산
   └─ 부서 드롭다운 + 작업자 리스트 응답
```

## 3. 백엔드 소견

### 3.1 일반 코드 리뷰
- **[상] views.py 451줄 모놀리식 + 페이지/API/비즈니스 혼재**
  HTML 렌더 함수 11개, API view 6개, 비즈니스 로직(달력 매핑·필터·prefetch)이 한 파일. 도메인별 책임 분리 시급.
- **[중] 함수 본문 안 import**
  [views.py:266-275](../../../drf-server/apps/dashboard/views.py#L266-L275), [364-365](../../../drf-server/apps/dashboard/views.py#L364-L365), [275](../../../drf-server/apps/dashboard/views.py#L275) 등에서 `from apps.X import Y`를 함수 안에 둠. 순환 import 회피 임시 패턴인 듯하나 매번 호출 시 import 비용 + 코드 가독성 저하. 모듈 상단으로 옮기거나 `apps.dashboard.selectors`로 위임.
- **[중] AllowAny + Session 데이터 = 권한 모호**
  [VRProgressView](../../../drf-server/apps/dashboard/views.py#L106), [MySafetyStatusView](../../../drf-server/apps/dashboard/views.py#L151)가 `AllowAny`인데 세션 기반 데이터 저장. JWT 환경에서 anonymous user가 세션 쿠키만 갖고 진행률·완료 상태를 저장 가능 → 의도와 다른 동작. `IsAuthenticated`로 변경 후 `request.user.id` 키로 저장 권장.
- **[중] selectors/services 부재**
  apps/dashboard에 selectors/, services/ 폴더 없음. SafetyHistoryAPIView가 직접 `SafetyStatus.objects.filter(...).values_list(...)` 조회. apps/safety는 풀 레이어 구조인데 dashboard에서 직접 safety의 모델을 import해 쿼리 → 도메인 경계 침범.
- **[중] 광범위 except**
  [MenuView.get:90-96](../../../drf-server/apps/dashboard/views.py#L90-L96) `try: get_menu_tree(...) except Exception: return 500`. 어떤 예외인지 알 수 없으니 디버깅 어려움 + 의도치 않은 예외도 500으로 묻힘.
- **[하] inline_serializer 과다**
  views.py 내 `inline_serializer` 정의가 ~10개. dashboard/serializers.py 신설 후 분리 시 가독성 개선.
- **[하] page view 중복**
  9개 함수 뷰가 모두 `def X_page(request): return render(request, "...")` — `path()` + `TemplateView.as_view(template_name=...)` 또는 `RoutableView`로 압축 가능.

### 3.2 아키텍처/레이어
- **[상] dashboard 앱이 cross-domain 호출의 허브가 됨**
  SafetyHistoryAPIView는 safety, WorkerListAPIView는 accounts·positioning 모델 직접 import. 도메인 경계 흐릿.
  → 옵션 A: `apps/safety/views/`에 history API를 두고 dashboard는 페이지만.
  → 옵션 B: dashboard가 BFF(Backend for Frontend) 역할이라면 selectors로 cross-domain 조회 캡슐화.
- **[중] 페이지 뷰의 인증 미적용 + 클라이언트 의존**
  HTML 페이지는 누구나 GET 가능. 인증은 JS의 Auth.getMe()로 클라이언트 측 리다이렉트. 검색 엔진 크롤링·캐시 노출은 차단되지만, **페이지 마크업이 SEO·미인증 사용자에게 노출**될 수 있음. 민감 정보가 SSR에 들어있지 않다면 문제 없으나, `event_id` 같은 path parameter는 공개됨. 페이지 뷰에 `@login_required` 또는 미들웨어로 일관 처리 권장.

### 3.3 보안 관점 (요약)
- **[중] AllowAny VR/안전 API의 세션 키 충돌 가능**
  같은 브라우저로 다른 사용자가 로그인해도 세션이 그대로면 이전 사용자의 진도·체크리스트가 유지됨. user별 격리 안 됨.
- **[하] worker_id로 다른 사용자 이력 조회 (관리자)**
  [SafetyHistoryAPIView.get:264-271](../../../drf-server/apps/dashboard/views.py#L264-L271) facility_admin이 자기 공장 외부 작업자도 조회 가능 (체크 없음). super_admin과 동일 권한 — facility_admin은 facility 범위 제한 권장.

## 4. 프론트엔드(JS/HTML) 소견

### 4.1 백엔드 contract 정합성
- **[중] dashboard/websocket.js와 fastapi build_broadcast_payload 키 정합**
  `/ws/sensors/` 페이로드는 `equipment[]`, `total_power_kw`, gas 측정값, `alarms[]`, `worker_positions` 키 혼합. 백엔드 키 변경 시 detail 페이지 5개+ JS가 전부 깨짐. **타입 contract 명세 부재** — 09 도메인에서 종합.

### 4.2 DOM 조작/렌더링 패턴
- **[중] 패널별 자체 렌더링 (App-level 상태 없음)**
  panels/event-panel.js, map-panel.js 등이 각각 fetch + DOM 조작. 같은 데이터를 두 패널이 쓰면 fetch 두 번 + 동기화 어려움. 작은 규모에선 OK이나 현재 6개 패널로 한계 근접.
- **[하] safety_history.js의 달력 렌더링 로직**
  서버가 `records[]`로 일자별 row 반환 → JS가 그리드 매핑. 서버가 calendar grid 자체를 만들어 보내면 JS 단순화 가능 (대신 응답 크기 약간 증가).

### 4.3 페이지 진입 인증 패턴
- **[중] 페이지마다 동일한 "init → Auth.getMe → 리다이렉트" 보일러플레이트**
  대시보드·서브페이지 모두 진입 시 `Auth.getMe()` 호출. 미인증 시 `/accounts/login/` 리다이렉트. 같은 패턴이 ~10개 JS 파일에 반복. `shared/page-init.js::requireAuth(callback)` 추출.

## 5. 개선 제안

### C1. dashboard/views.py 분리 + 레이어 정착 [상 · 대]
- **왜 필요?**: 451줄에 페이지/API/비즈니스 로직 혼재. 컨벤션 위반·테스트 어려움·도메인 경계 흐림.
- **장점**: 책임 분리·테스트 용이·dashboard 도메인이 BFF로 명확해짐.
- **단점**: 큰 PR (페이지 뷰는 ​​[urls.py](../../../drf-server/apps/dashboard/urls.py)만 변경, API 분리는 import 경로 갱신).
- **변경 위치**: 신규 [views/pages.py](../../../drf-server/apps/dashboard/views/), [views/menu_api.py](../../../drf-server/apps/dashboard/views/), [views/safety_api.py](../../../drf-server/apps/dashboard/views/), [views/workers_api.py](../../../drf-server/apps/dashboard/views/) + selectors/, services/ 폴더.

### C2. AllowAny VR/안전 API → IsAuthenticated [상 · 소]
- **왜 필요?**: 같은 브라우저로 다른 사용자 로그인 시 진도가 섞임. 세션 키가 user별 격리 안 됨.
- **장점**: 사용자 격리 / 인증 일관성.
- **단점**: 페이지 진입 시점 + 세션 만료 시 401 처리 추가 필요 (이미 auth.js가 처리).
- **변경 위치**: [VRProgressView:107](../../../drf-server/apps/dashboard/views.py#L107), [MySafetyStatusView:152](../../../drf-server/apps/dashboard/views.py#L152). 세션 키도 `f"safety_{user.id}_checklist_done_date"`로 격리.

### C3. 안전확인 진실 원천 단일화 (세션 → DB) [상 · 중]
- **왜 필요?**: 현재 "오늘 완료"는 세션에, 월별 히스토리는 SafetyStatus 모델에. 두 곳이 어긋나면 사용자가 "체크 완료했는데 히스토리에 안 보임" 사고.
- **장점**: 단일 원천 / 다른 디바이스에서도 일관 / 쿼리 효율.
- **단점**: SafetyStatus 모델의 today 조회가 매번 발생 (캐시 가능).
- **변경 위치**: VRProgressView/MySafetyStatusView를 apps.safety.services로 위임 — 세션 제거하고 SafetyStatus.objects.update_or_create.

### C4. 페이지 뷰 인증 통일 [중 · 소]
- **왜 필요?**: HTML 페이지가 무인증으로 노출. 미인증 사용자에게 마크업이 보이는 건 보안 경계로 약함.
- **장점**: 명시적 인증 경계 / SEO/캐시 노출 제어.
- **단점**: SPA 진입 흐름 변경 필요 (현재 클라이언트 redirect 의존).
- **변경 위치**: dashboard.urls.py에 `@login_required` 데코레이터 또는 `LoginRequiredMixin`. JWT-only면 미들웨어로 access_token 쿠키 검증.

### C5. cross-domain 조회 캡슐화 [중 · 중]
- **왜 필요?**: dashboard.views가 safety, accounts, positioning 모델을 직접 import → 도메인 경계 침범.
- **장점**: 도메인 변경 시 영향 격리.
- **단점**: 한 번의 BFF 패턴 정립 필요 (학습 비용).
- **변경 위치**: [apps/dashboard/selectors/cross_domain.py](../../../drf-server/apps/dashboard/) 신규. 또는 각 도메인의 selectors가 호출 인터페이스 노출.

### C6. 광범위 except → 구체 예외 [중 · 소]
- **왜 필요?**: `except Exception`은 의도치 않은 예외도 묻힘. 운영 디버깅 시 원인 추적 불가.
- **장점**: 진짜 에러는 500/sentry로 노출, 비즈니스 예외만 친절 메시지.
- **단점**: 예외 타입 학습 필요.
- **변경 위치**: [MenuView.get:92](../../../drf-server/apps/dashboard/views.py#L92), 비슷한 패턴들.

### C7. inline_serializer → schemas.py 분리 [하 · 중]
- **왜 필요?**: dashboard/views.py에 inline_serializer가 10개+. 가독성·재사용 저하.
- **변경 위치**: [apps/dashboard/schemas.py](../../../drf-server/apps/dashboard/) 신규.

### C8. JS shared/page-init 추출 [하 · 소]
- **왜 필요?**: 페이지마다 Auth.getMe → 권한 체크 보일러플레이트 반복.
- **장점**: 추가 페이지 작성 시 1줄로 인증 보장.
- **변경 위치**: [shared/page-init.js](../../../drf-server/static/js/shared/) 신규.

### C9. facility_admin 데이터 범위 검증 [중 · 소]
- **왜 필요?**: facility_admin이 worker_id 파라미터로 자기 공장 외부 작업자 이력 조회 가능.
- **장점**: 권한 모델 일관 / 정보 누출 차단.
- **단점**: 없음.
- **변경 위치**: [SafetyHistoryAPIView:264-271](../../../drf-server/apps/dashboard/views.py#L264-L271)에 facility 일치 체크 추가.

### C10. 함수 안 import 제거 [하 · 소]
- **왜 필요?**: 함수 호출마다 import 오버헤드 + 가독성.
- **변경 위치**: [views.py:266, 275, 364-365](../../../drf-server/apps/dashboard/views.py#L266) 등.

## 6. 구현 추천 순서

### 1단계 — 권한 정합성 (즉시) ⚡
- **C2** AllowAny → IsAuthenticated (1 라인 + 세션 키 변경)
- **C9** facility_admin 범위 검증 (3~5줄)
- **C6** 광범위 except 구체화
- **이유**: 사용자 데이터 격리는 즉시 시급. 변경 작은데 효과 큼.

### 2단계 — 진실 원천 통일 (1주 내) 🔄
- **C3** 안전확인 세션 → DB
- **이유**: 사용자 사고("내가 한 게 사라짐") 직결. C2 적용 후 안정된 상태에서 진행.

### 3단계 — 아키텍처 정리 (다음 sprint) 🏗
- **C1** views.py 분리 + selectors/services 정착
- **C5** cross-domain 캡슐화 (C1과 함께)
- **C7** schemas.py 분리
- **이유**: 큰 작업 1회로 묶어서 진행 권장. 컨벤션 정합성 확보.

### 4단계 — 인증·UX 일관성 (여유 시) ✨
- **C4** 페이지 뷰 인증 통일
- **C8** JS shared/page-init
- **C10** 함수 안 import 제거

### ⚠️ 주의사항 (초보자용)
- **C2 변경 시 세션 키 마이그레이션**: 기존에 `safety_checklist_done_date`로 저장된 세션 데이터가 있다면 사용자가 오늘 한 번 더 체크해야 함 (운영 공지 또는 호환 코드).
- **C3은 안전 도메인 시그널 의존 가능**: SafetyStatus가 다른 시그널/Celery로 갱신된다면 충돌 점검 필요.
- **C1은 PR을 도메인별로 쪼개기**: 페이지 뷰 분리 / API 도메인별 분리 / selectors 도입을 분리된 PR로 진행해야 리뷰·롤백 쉬움.
