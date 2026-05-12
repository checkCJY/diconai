# [기능정의서] 어드민 API — 공지사항 관리 + 로그 조회 4종

> 작성자: 정휘훈 | 브랜치: `feature/admin-api` | 작성일: 2026-05-12

---

## 1. 기능 목록표

| 대분류 | 화면명 | 기능ID | 기능명 | 기능 목적 |
|--------|--------|--------|--------|-----------|
| 공지사항 | 공지사항 목록 | NTC-01 | 공지사항 목록 조회 | 등록된 공지사항을 페이지네이션·필터로 조회 |
| 공지사항 | 공지사항 등록 | NTC-02 | 공지사항 등록 | 제목·내용·카테고리·첨부파일 포함 공지 생성 |
| 공지사항 | 공지사항 상세 | NTC-03 | 공지사항 상세 조회 | 단건 공지 + 첨부파일 목록 반환 |
| 공지사항 | 공지사항 수정 | NTC-04 | 공지사항 수정 | 부분 수정(PATCH) + 변경 이력 기록 |
| 공지사항 | 공지사항 삭제 | NTC-05 | 공지사항 소프트 삭제 | DB 보존 + is_deleted 플래그로 삭제 처리 |
| 공지사항 | 공지사항 상세 | NTC-06 | 첨부파일 업로드 | 공지 단건에 파일 추가 (10MB 제한) |
| 공지사항 | 공지사항 상세 | NTC-07 | 첨부파일 삭제 | storage 파일 + DB 레코드 동시 삭제 |
| 로그 | 시스템 로그 | LOG-01 | 시스템 로그 조회 | AppLog(운영 로그) 목록 조회 |
| 로그 | 사용자 활동 로그 | LOG-02 | 사용자 활동 로그 조회 | SystemLog(감사 로그) 목록 조회 |
| 로그 | 연동 로그 | LOG-03 | 연동 로그 조회 | IntegrationLog(시스템 간 연동) 목록 조회 |
| 로그 | 지도 편집 로그 | LOG-04 | 지도 편집 로그 조회 | SystemLog 중 MAP_ action만 조회 |
| 지도 편집 | 지도 편집기 | MAP-01 | 지도 편집 행위 기록 | 저장 시 편집 내역을 SystemLog에 자동 기록 |

---

## 2. 요구사항 정의서

### [REQ-NTC] 공지사항 관리

- **분류**: 기능적 요구사항
- **중요도**: 상
- **기능 목적**: 관리자가 공지사항을 CRUD 관리하고, 모든 행위가 사용자 활동 로그에 기록됨

**요구사항 상세**
- 목록 조회: category(general/urgent/maintenance) · keyword(제목) · is_pinned 필터 지원
- category 유효성: 허용되지 않은 값 입력 시 400 + `{"error": "invalid category", "allowed": [...]}` 반환 (조용히 무시하지 않음 — 잘못된 필터로 전체 목록이 노출되는 오해 방지)
- 소프트 삭제: `is_deleted=True` + `deleted_at` + `deleted_by` 3개 컬럼 기록. `DELETE` 이후에도 DB에 데이터가 남아 이력 추적 가능
- 감사 로그: 등록(notice_create) · 수정(notice_update) · 삭제(notice_delete) 시 `log_action()` 호출 → SystemLog 자동 기록
- 수정 시 old_value/new_value 스냅샷 저장 → 어떤 내용이 어떻게 바뀌었는지 추적 가능

**백엔드 처리**
- 권한: `IsSuperAdminOrFacilityAdmin` (슈퍼관리자 + 시설관리자 모두 접근 가능)
- 페이지네이션: `AdminPagination` → `{ results, total, page, page_size, has_next }` 응답 구조
- 첨부파일: `MultiPartParser + FormParser` 사용, `full_clean()` 명시 호출로 validators 실행 (save()는 자동 실행 안 함)
- IP 기록: `X-Forwarded-For` 헤더 우선, 없으면 `REMOTE_ADDR` fallback

**예외 사항**
- 소프트 삭제된 공지는 `_get_notice()` 헬퍼에서 `filter(is_deleted=False)`로 걸러 404 반환
- 다른 공지의 첨부파일 삭제 시도 방지: `get_object_or_404(NoticeAttachment, pk=att_id, notice_id=pk)`

---

### [REQ-LOG] 로그 조회 4종

- **분류**: 기능적 요구사항
- **중요도**: 상
- **기능 목적**: 운영 중 발생한 시스템 로그 · 사용자 활동 · 연동 이력 · 지도 편집 이력을 관리자가 조회

**요구사항 상세**
- 모든 로그 API: GET 전용 (로그는 APPEND-ONLY — 모델 레벨에서 수정·삭제 차단)
- 날짜 파싱 실패(잘못된 형식)는 해당 필터를 조용히 무시 — 날짜 오타로 전체 목록이 안 보이는 상황 방지
- 날짜 범위 종료일: `date_to + 1일 미만(lt)` 처리로 해당 날짜 23:59:59까지 포함
- 사용자 활동 로그 / 지도 편집 로그는 동일 모델(SystemLog)을 `action_type` prefix로 분리

**사용자 활동 로그 vs 지도 편집 로그 분리 이유**
- 사용자 활동 로그: MAP_ 제외 전체 + result 필터 + actor 필터
- 지도 편집 로그: MAP_ 전용 + target_name 검색 + result 필터 없음
- 화면 설계상 탭이 다르고 필터 항목도 다름 → 뷰 분리로 사이드이펙트 방지

**권한**
- 4개 API 모두 `IsSuperAdminOrFacilityAdmin`

---

### [REQ-MAP-01] 지도 편집 로그 자동 기록

- **분류**: 기능적 요구사항
- **중요도**: 중
- **기능 목적**: 지도 편집기에서 저장 버튼 클릭 시 편집 내역이 SystemLog에 자동 기록됨

**요구사항 상세**
- 저장 단위: 한 번의 저장 요청에 여러 객체가 포함될 수 있으므로 각 객체마다 `log_action()` 1회씩 호출
- 기록 대상: 설비 위치/크기 수정, 가스센서 이동, 전력장치 이동, 위치노드 이동, 위험구역 생성, 위험구역 삭제
- 트랜잭션: `@transaction.atomic` 내에서 처리 — 저장 실패 시 로그도 롤백

---

## 3. 흐름도 (파이프라인)

### 3-1. 공지사항 등록 흐름

```
클라이언트
  │
  ├─ POST /api/admin/notices/
  │        ↓
  │   [IsSuperAdminOrFacilityAdmin 권한 검사]
  │        ↓ 403 if 권한 없음
  │   [NoticeCreateUpdateSerializer.is_valid()]
  │        ↓ 400 if 유효성 실패
  │   notice = serializer.save(author=request.user, updated_by=request.user)
  │        ↓
  │   [log_action(actor_id, "notice_create", target_model="Notice", ...)]
  │        ↓
  │   SystemLog.objects.create(...)   ← APPEND-ONLY INSERT
  │        ↓
  │   201 + NoticeDetailSerializer(notice).data
  └─ 응답
```

### 3-2. 공지사항 소프트 삭제 흐름

```
클라이언트
  │
  ├─ DELETE /api/admin/notices/{pk}/
  │        ↓
  │   [IsSuperAdminOrFacilityAdmin 권한 검사]
  │        ↓
  │   _get_notice(pk)
  │     → Notice.objects.filter(is_deleted=False).select_related(...)
  │     → get_object_or_404(...)  ← 이미 삭제된 공지면 404
  │        ↓
  │   notice.is_deleted = True
  │   notice.deleted_at = timezone.now()
  │   notice.deleted_by = request.user
  │   notice.save(update_fields=["is_deleted","deleted_at","deleted_by"])
  │        ↓
  │   [log_action(actor_id, "notice_delete", old_value={title, category})]
  │        ↓
  │   204 No Content
  └─ 응답
```

### 3-3. 사용자 활동 로그 조회 흐름

```
클라이언트
  │
  ├─ GET /api/admin/activity-logs/?actor=홍길동&date_from=2026-05-01
  │        ↓
  │   [IsSuperAdminOrFacilityAdmin 권한 검사]
  │        ↓
  │   SystemLog.objects.exclude(action_type__startswith="map_")
  │        ↓
  │   [필터 체인]
  │   → actor_keyword → Q(actor__username__icontains) | Q(actor__email__icontains)
  │   → action_type   → 유효값 검증 후 filter
  │   → result        → 유효값 검증 후 filter
  │   → keyword       → description__icontains
  │   → date_from     → _parse_date() → created_at__gte
  │   → date_to       → _parse_date() → created_at__lt (date_to + 1일)
  │        ↓
  │   .order_by("-created_at")
  │        ↓
  │   AdminPagination.paginate_queryset(qs, request)
  │        ↓
  │   SystemLogAdminSerializer(page, many=True)
  │        ↓
  │   200 + { results, total, page, page_size, has_next }
  └─ 응답
```

### 3-4. 지도 편집 저장 + 로그 기록 흐름

```
지도 편집기 화면
  │
  ├─ POST /api/map-editor/save/  { facilities:[...], gas_sensors:[...], geofences:[...] }
  │        ↓
  │   [@transaction.atomic]
  │        ↓
  │   MapEditorSaveSerializer.is_valid()
  │        ↓ 400 if 실패
  │   actor_id = request.user.pk
  │   ip = X-Forwarded-For or REMOTE_ADDR
  │        ↓
  │   [for each facility]
  │     Facility.objects.filter(pk=id).update(map_x, map_y, ...)
  │     log_action(actor_id, "map_facility_update", target_model="Facility")
  │        ↓
  │   [for each gas_sensor]
  │     GasSensor.objects.filter(pk=id).update(x, y)
  │     log_action(actor_id, "map_sensor_move", target_model="GasSensor")
  │        ↓
  │   [for each power_device]
  │     PowerDevice.objects.filter(pk=id).update(x, y)
  │     log_action(actor_id, "map_facility_update", target_model="PowerDevice")
  │        ↓
  │   [for each position_node]
  │     PositionNode.objects.filter(pk=id).update(x, y)
  │     log_action(actor_id, "map_position_node_register", target_model="PositionNode")
  │        ↓
  │   [for each geofence]
  │     if deleted=True → GeoFence.update(is_active=False)
  │                     → log_action("map_object_delete")
  │     elif id 존재   → GeoFence.update(name, risk_level, polygon, ...)
  │     else           → gf = GeoFence.create(...)
  │                     → log_action("map_geofence_create", target_id=gf.pk)
  │        ↓
  │   200 + { saved: true, updated: { facilities, gas_sensors, ... } }
  └─ 응답

  ※ log_action()은 모두 SystemLog.objects.create() INSERT
  ※ @transaction.atomic — 저장 실패 시 로그도 함께 롤백
```

### 3-5. 시스템 로그(AppLog) 데이터 유입 흐름

```
앱 코드 어딘가
  logger.error("뭔가 잘못됨")
        ↓
  [Python logging 프레임워크]
        ↓
  DBLogHandler.emit(record)      ← settings.LOGGING에 등록, level=ERROR 이상만 처리
        ↓
  [재귀 가드: thread-local _guard]  ← emit 중 또 logger.error() 호출 시 무한루프 방지
        ↓
  applog_create_task.delay(...)  ← Celery 비동기 INSERT (web pod latency 0)
        ↓ (broker 다운 시 fallback)
  AppLog.objects.create(log_category, service_module, level, message)
        ↓
  GET /api/admin/system-logs/ 조회 시 화면에 표시

  [log_category 자동 분류 로직]
  - logger name에 "celery/batch/task" 포함 → "batch"
  - ERROR 이상 레벨 → "error"
  - 그 외 → "service"
```

### 3-6. 연동 로그(IntegrationLog) 데이터 유입 흐름

```
[경로 1 — DRF 내부 Celery task]

가스센서 위험 수치 감지
        ↓
fire_danger_alarm_task (Celery)
        ↓
_push_to_ws(alarm_data)
  → httpx.post(FastAPI WS 브로드캐스트 URL, ...)
  → result = "success" or "failure"
        ↓
integration_log_create_task.delay(
  integration_type="transmit",
  target_system="DRF→FastAPI",
  result=result,
  description="alarm_type=DANGER_GAS"
)
        ↓
IntegrationLog.objects.create(...)


[경로 2 — FastAPI → DRF 직접 기록]

FastAPI 수집/동기화 작업 완료
        ↓
POST /api/internal/integration-logs/  (localhost-only, JWT 우회)
        ↓
IntegrationLogInternalCreateView
        ↓
IntegrationLog.objects.create(...)
```

---

## 4. API 명세서

### NTC-01 | 공지사항 목록 조회

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| URL | `/api/admin/notices/` |
| 권한 | IsSuperAdminOrFacilityAdmin |

**Query Params**
| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| category | string | 선택 | `general` \| `urgent` \| `maintenance` |
| keyword | string | 선택 | 제목 부분 일치 검색 |
| is_pinned | boolean | 선택 | 상단 고정 여부 |
| page | int | 선택 | 기본값 1 |
| page_size | int | 선택 | 기본값 10 |

**Response 200**
```json
{
  "results": [
    {
      "id": 1,
      "title": "5월 정기 점검 안내",
      "category": "maintenance",
      "is_active": true,
      "is_pinned": false,
      "author_name": "홍길동",
      "published_at": "2026-05-01T09:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 10,
  "has_next": false
}
```

**Response 400 (잘못된 category)**
```json
{
  "error": "invalid category",
  "allowed": ["general", "urgent", "maintenance"]
}
```

---

### NTC-02 | 공지사항 등록

| 항목 | 내용 |
|------|------|
| 메서드 | POST |
| URL | `/api/admin/notices/` |
| Content-Type | application/json |
| 권한 | IsSuperAdminOrFacilityAdmin |

**Request Body**
```json
{
  "title": "5월 정기 점검 안내",
  "content": "5월 15일 오전 2시~6시 점검 예정입니다.",
  "category": "maintenance",
  "is_active": true,
  "is_pinned": false
}
```

**Response 201**
```json
{
  "id": 1,
  "title": "5월 정기 점검 안내",
  "content": "...",
  "category": "maintenance",
  "is_active": true,
  "is_pinned": false,
  "author_name": "홍길동",
  "attachments": []
}
```

> 등록 성공 시 `SystemLog`에 `action_type="notice_create"` 자동 기록

---

### NTC-05 | 공지사항 소프트 삭제

| 항목 | 내용 |
|------|------|
| 메서드 | DELETE |
| URL | `/api/admin/notices/{id}/` |
| 권한 | IsSuperAdminOrFacilityAdmin |

**Response 204** (No Content)

> 삭제 성공 시 `SystemLog`에 `action_type="notice_delete"`, `old_value={title, category}` 기록
> DB에서 제거되지 않음 — `is_deleted=True`, `deleted_at`, `deleted_by` 기록

---

### NTC-06 | 첨부파일 업로드

| 항목 | 내용 |
|------|------|
| 메서드 | POST |
| URL | `/api/admin/notices/{id}/attachments/` |
| Content-Type | multipart/form-data |
| 권한 | IsSuperAdminOrFacilityAdmin |

**Request**
```
file: (binary)
```

**Response 201**
```json
{
  "id": 1,
  "filename": "점검계획서.pdf",
  "file_url": "http://localhost:8000/media/notices/점검계획서.pdf",
  "size": 204800
}
```

**제약**
- 파일 크기: 10MB 이하
- 허용 확장자: pdf, doc, docx, xls, xlsx, ppt, pptx, jpg, jpeg, png, zip

---

### LOG-01 | 시스템 로그 조회

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| URL | `/api/admin/system-logs/` |
| 권한 | IsSuperAdminOrFacilityAdmin |

**Query Params**
| 파라미터 | 설명 |
|----------|------|
| log_category | `error` \| `batch` \| `service` |
| keyword | message 또는 service_module 부분 일치 |
| date_from | YYYY-MM-DD |
| date_to | YYYY-MM-DD |
| page / page_size | 페이지네이션 |

**Response 200**
```json
{
  "results": [
    {
      "id": 1,
      "log_category": "error",
      "service_module": "apps.alerts.services",
      "level": "ERROR",
      "message": "가스센서 데이터 수신 실패: timeout",
      "created_at": "2026-05-12T10:30:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 10,
  "has_next": false
}
```

---

### LOG-02 | 사용자 활동 로그 조회

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| URL | `/api/admin/activity-logs/` |
| 권한 | IsSuperAdminOrFacilityAdmin |

**Query Params**
| 파라미터 | 설명 |
|----------|------|
| actor | username 또는 email 부분 일치 (OR 검색) |
| action_type | `notice_create` 등 SystemLog.ActionType 코드값 |
| result | `success` \| `failure` |
| keyword | description 부분 일치 |
| date_from / date_to | YYYY-MM-DD |

**Response 200**
```json
{
  "results": [
    {
      "id": 1,
      "actor_name": "홍길동",
      "action_type": "notice_create",
      "action_type_display": "공지 생성",
      "target_model": "Notice",
      "target_id": "3",
      "target_name": "",
      "result": "success",
      "result_display": "성공",
      "description": "공지사항 등록: 5월 정기 점검 안내",
      "ip_address": "172.20.0.1",
      "created_at": "2026-05-12T10:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 10,
  "has_next": false
}
```

---

### LOG-03 | 연동 로그 조회

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| URL | `/api/admin/integration-logs/` |
| 권한 | IsSuperAdminOrFacilityAdmin |

**Query Params**
| 파라미터 | 설명 |
|----------|------|
| integration_type | `collect` \| `transmit` \| `sync` |
| result | `success` \| `failure` \| `delay` |
| keyword | target_system 또는 description 부분 일치 |
| date_from / date_to | YYYY-MM-DD |

---

### LOG-04 | 지도 편집 로그 조회

| 항목 | 내용 |
|------|------|
| 메서드 | GET |
| URL | `/api/admin/map-edit-logs/` |
| 권한 | IsSuperAdminOrFacilityAdmin |

**Query Params**
| 파라미터 | 설명 |
|----------|------|
| action_type | `map_geofence_create` \| `map_sensor_move` \| `map_facility_update` \| `map_position_node_register` \| `map_object_delete` |
| keyword | target_name 또는 description 부분 일치 |
| date_from / date_to | YYYY-MM-DD |

---

## 5. 주요 함수/클래스 설명

### `log_action()` — `apps/core/services/audit_service.py`

```python
log_action(
    actor_id,       # 행위자 User PK
    action_type,    # SystemLog.ActionType 코드값 (예: "notice_create")
    target_model,   # 대상 모델명 (예: "Notice")
    target_id,      # 대상 레코드 PK
    old_value,      # 수정 전 값 스냅샷 (dict, 수정/삭제 시)
    new_value,      # 수정 후 값 스냅샷 (dict, 등록/수정 시)
    description,    # 사람이 읽을 수 있는 설명
    ip_address,     # 요청자 IP
)
```

모든 관리자 행위 로그는 이 함수를 통해 `SystemLog.objects.create()` 1회 호출로 처리된다.

---

### `SystemLogAdminSerializer` — `apps/core/serializers/system_log_serializers.py`

- `actor_name`: `SerializerMethodField` — actor가 NULL(탈퇴 관리자)이면 `"탈퇴한 관리자"` 반환, 이름 미입력이면 username 반환
- `action_type_display`: `get_action_type_display()` — TextChoices 한글 표시값
- `result_display`: `get_result_display()` — "success" → "성공"

사용자 활동 로그와 지도 편집 로그 두 API에서 공용으로 사용 (같은 SystemLog 모델)

---

### `_parse_date()` — log_views.py, system_log_views.py

```python
def _parse_date(value: str):
    # "YYYY-MM-DD" → timezone-aware datetime
    # 파싱 실패 → None (해당 필터 조용히 무시)
```

날짜 오타로 전체 목록이 안 보이는 상황을 방지하기 위해 실패 시 None 반환.

---

### `_get_client_ip()` — notice_views.py

```python
def _get_client_ip(request):
    # X-Forwarded-For 우선 (nginx 프록시 환경)
    # 없으면 REMOTE_ADDR fallback
    # X-Forwarded-For에 여러 IP가 콤마로 있으면 첫 번째(원본 클라이언트) 반환
```

---

### `DBLogHandler.emit()` — `apps/operations/logging/db_handler.py`

- Python logging → AppLog INSERT 담당
- `level=ERROR` 이상만 처리 (settings.LOGGING 설정)
- Celery `applog_create_task.delay()` 비동기 INSERT → broker 다운 시 동기 fallback
- thread-local `_guard`로 재귀 무한루프 방지
- `_infer_category()`: logger name 기반 자동 분류 (celery/batch/task → "batch", ERROR → "error", else → "service")

---

## 6. 디렉토리 구조

```
drf-server/
├── apps/
│   ├── core/
│   │   ├── admin_urls.py                        # 사용자 활동·지도 편집 로그 API URL
│   │   ├── models/system_log.py                 # SystemLog 모델 (APPEND-ONLY)
│   │   ├── serializers/system_log_serializers.py # SystemLogAdminSerializer
│   │   ├── services/audit_service.py            # log_action() 헬퍼
│   │   └── views/system_log_views.py            # SystemLogAdminListView, MapEditLogAdminListView
│   ├── notices/
│   │   ├── migrations/0002_add_soft_delete_to_notice.py  # is_deleted 컬럼 추가
│   │   ├── models/notice.py                     # is_deleted, deleted_at, deleted_by 추가
│   │   ├── serializers/                         # NoticeListSerializer 등
│   │   ├── urls.py                              # 공지사항 API URL
│   │   └── views/notice_views.py                # NoticeListView, NoticeDetailView, NoticeAttachmentView
│   ├── operations/
│   │   ├── models/app_log.py                    # AppLog 모델 (시스템 로그)
│   │   ├── models/integration_log.py            # IntegrationLog 모델
│   │   ├── logging/db_handler.py                # DBLogHandler (Python logging → AppLog)
│   │   ├── tasks/integration_log_task.py        # Celery 비동기 IntegrationLog INSERT
│   │   └── views/admin/log_views.py             # AppLogAdminListView, IntegrationLogAdminListView
│   └── facilities/
│       └── views/map_editor.py                  # MapEditorSaveView (log_action 추가)
├── config/
│   ├── urls.py                                  # api/admin/ include 등록
│   └── admin_panel_urls.py                      # 로그·공지사항 화면 URL 등록
├── templates/admin_panel/
│   ├── notices/                                 # 공지사항 화면 4종 (목록/상세/등록/수정)
│   └── logs/                                    # 로그 화면 4종
├── static/
│   ├── css/admin/
│   │   ├── notices.css                          # 공지사항 스타일
│   │   └── logs.css                             # 로그 공통 스타일
│   └── js/admin/
│       ├── notices/                             # 공지사항 JS 3종
│       └── logs/                               # 로그 JS 5종 (log_utils + 4종)
```

---

## 7. URL 정의서

### API URL

| 메서드 | URL | 설명 | 파일 |
|--------|-----|------|------|
| GET | `/api/admin/notices/` | 공지사항 목록 | notices/urls.py |
| POST | `/api/admin/notices/` | 공지사항 등록 | notices/urls.py |
| GET | `/api/admin/notices/{id}/` | 공지사항 상세 | notices/urls.py |
| PATCH | `/api/admin/notices/{id}/` | 공지사항 수정 | notices/urls.py |
| DELETE | `/api/admin/notices/{id}/` | 공지사항 소프트 삭제 | notices/urls.py |
| POST | `/api/admin/notices/{id}/attachments/` | 첨부파일 업로드 | notices/urls.py |
| DELETE | `/api/admin/notices/{id}/attachments/{att_id}/` | 첨부파일 삭제 | notices/urls.py |
| GET | `/api/admin/system-logs/` | 시스템 로그 조회 | operations/urls.py |
| GET | `/api/admin/integration-logs/` | 연동 로그 조회 | operations/urls.py |
| GET | `/api/admin/activity-logs/` | 사용자 활동 로그 조회 | core/admin_urls.py |
| GET | `/api/admin/map-edit-logs/` | 지도 편집 로그 조회 | core/admin_urls.py |

### 어드민 패널 페이지 URL

| URL | 화면 | 파일 |
|-----|------|------|
| `/admin-panel/notices/` | 공지사항 목록 | config/admin_panel_urls.py |
| `/admin-panel/notices/create/` | 공지사항 등록 | config/admin_panel_urls.py |
| `/admin-panel/notices/{id}/` | 공지사항 상세 | config/admin_panel_urls.py |
| `/admin-panel/notices/{id}/edit/` | 공지사항 수정 | config/admin_panel_urls.py |
| `/admin-panel/logs/system/` | 시스템 로그 | config/admin_panel_urls.py |
| `/admin-panel/logs/activity/` | 사용자 활동 로그 | config/admin_panel_urls.py |
| `/admin-panel/logs/integration/` | 연동 로그 | config/admin_panel_urls.py |
| `/admin-panel/logs/map-edit/` | 지도 편집 로그 | config/admin_panel_urls.py |

---

## 8. 모델 변경 사항

### Notice 모델 — 소프트 삭제 필드 추가 (migration: 0002)

```python
is_deleted  = BooleanField(default=False)
deleted_at  = DateTimeField(null=True, blank=True)
deleted_by  = ForeignKey(User, on_delete=SET_NULL, null=True, related_name="notices_deleted")
```

- 기존 `notice.delete()` → `notice.is_deleted=True + save(update_fields=[...])`로 교체
- 모든 queryset에 `filter(is_deleted=False)` 조건 추가
- 삭제된 공지에 첨부파일 업로드 시도 시 404 반환

---

## 9. 로그 데이터 유입 기준 요약

| 로그 종류 | 테이블 | 데이터가 쌓이는 조건 |
|-----------|--------|----------------------|
| 시스템 로그 | `app_log` | `logger.error()` 등 Python logging ERROR 이상 호출 시 자동 |
| 사용자 활동 로그 | `system_log` | `log_action()` 명시 호출 시 (현재: 공지사항 3종 + 지오펜스 수정 + 장비 비활성화) |
| 연동 로그 | `integration_log` | 가스센서 알람 발생 → FastAPI WS 푸시 결과, 또는 FastAPI → DRF 직접 호출 시 |
| 지도 편집 로그 | `system_log` | 지도 편집기 저장 버튼 클릭 시 자동 (MAP_ action_type으로 system_log에 기록) |
