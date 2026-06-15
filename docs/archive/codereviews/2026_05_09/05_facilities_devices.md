# 05. 설비·장치 (Facilities · Equipments · Gas Sensors · Power Devices · Map Editor)

## 1. 범위

### 1.1 API 엔드포인트
| URL | 메서드 | 뷰 | 권한 |
|---|---|---|---|
| `/api/facilities/` | GET | FacilityAdminListView | IsSuperAdmin |
| `/api/facilities/<id>/` | GET, PUT, DELETE | FacilityAdminDetailView | IsSuperAdmin |
| `/api/facilities/bulk-delete/` | POST | FacilityAdminBulkDeleteView | IsSuperAdmin |
| `/api/facilities/select/` | GET | FacilitySelectView | IsSuperAdmin |
| `/api/facilities/power-device-options/` | GET | FacilityPowerDeviceOptionsView | IsSuperAdmin |
| `/api/equipments/`, `/api/equipments/<id>/`, `/api/equipments/bulk-delete/` | CRUD | EquipmentAdminListView/DetailView/BulkDeleteView | IsSuperAdmin |
| `/api/gas-sensors/`, `/api/gas-sensors/<id>/`, `/api/gas-sensors/bulk-delete/` | CRUD | GasSensorAdminListView/DetailView/BulkDeleteView | IsSuperAdmin |
| `/api/gas-sensors/next-code/` | GET | GasSensorNextCodeView | IsSuperAdmin |
| `/api/gas-sensors/check-connection/` | POST | GasSensorConnectionCheckView | IsSuperAdmin |
| `/api/gas-sensors/<id>/inspections/` | GET | GasSensorInspectionListView | IsSuperAdmin |
| `/api/gas-sensors/inspections/<id>/action/` | POST | GasSensorInspectionActionView | IsSuperAdmin |
| `/api/power-devices/`, `/<id>/`, `/codes/`, `/next-code/`, `/check-connection/`, `/bulk-delete/`, `/<id>/inspections/`, `/inspections/<id>/action/` | CRUD+ | PowerDeviceAdmin* views | IsSuperAdmin |
| `/api/map-editor/objects/` | GET | MapEditorObjectsView | IsSuperAdmin |
| `/api/map-editor/save/` | POST | MapEditorSaveView | IsSuperAdmin |
| `/api/departments/select/` | GET | DepartmentSelectView | IsSuperAdmin |
| `/api/managers/select/` | GET | ManagerSelectView | IsSuperAdmin |

### 1.2 백엔드 파일 (총 1818줄, 분리 시급)
- [drf-server/apps/facilities/views/facility_admin.py](../../../../drf-server/apps/facilities/views/facility_admin.py) — **668줄** (시설+설비+전력장치 일부)
- [drf-server/apps/facilities/views/gas_sensor_admin.py](../../../../drf-server/apps/facilities/views/gas_sensor_admin.py) — **485줄**
- [drf-server/apps/facilities/views/power_device_admin.py](../../../../drf-server/apps/facilities/views/power_device_admin.py) — **453줄**
- [drf-server/apps/facilities/views/map_editor.py](../../../../drf-server/apps/facilities/views/map_editor.py) — 212줄
- [drf-server/apps/facilities/selectors/{active_devices,admin_devices}.py](../../../../drf-server/apps/facilities/selectors/)
- [drf-server/apps/facilities/services/{device_service,threshold_service}.py](../../../../drf-server/apps/facilities/services/)
- [drf-server/apps/facilities/models/{facility,equipment,devices,gas_sensor_inspection,power_device_inspection,thresholds}.py](../../../../drf-server/apps/facilities/models/)

### 1.3 프론트엔드 파일
- [drf-server/static/js/admin/facility/facility.js](../../../../drf-server/static/js/admin/facility/facility.js)
- [drf-server/static/js/admin/gas_sensor/gas_sensor.js](../../../../drf-server/static/js/admin/gas_sensor/gas_sensor.js)
- [drf-server/static/js/admin/power_system/power_system.js](../../../../drf-server/static/js/admin/power_system/power_system.js)
- [drf-server/static/js/admin/map_editor/map_editor.js](../../../../drf-server/static/js/admin/map_editor/map_editor.js)
- [drf-server/templates/admin_panel/facility/facility.html](../../../../drf-server/templates/admin_panel/facility/facility.html)
- [drf-server/templates/admin_panel/gas_sensor/gas_sensor.html](../../../../drf-server/templates/admin_panel/gas_sensor/gas_sensor.html)
- [drf-server/templates/admin_panel/power_system/power_system.html](../../../../drf-server/templates/admin_panel/power_system/power_system.html)
- [drf-server/templates/admin_panel/map_editor/map_editor.html](../../../../drf-server/templates/admin_panel/map_editor/map_editor.html)

## 2. 기능 흐름

### 2.1 시설/장치 관리 (대표 흐름)
```
1. /admin-panel/facility/ 페이지 → facility.js
2. GET /api/facilities/?q=X&is_active=true&page=1&page_size=20
   ├─ FacilityAdminListView.get
   ├─ Facility.objects.all().prefetch_related("powerdevices").select_related("manager")
   ├─ q 파라미터: "FAC-1" 같은 코드 prefix면 id 검색, 아니면 name__icontains
   ├─ AdminPagination
   └─ 200 OK 페이지 + 메타
3. JS 모달 → POST/PUT/DELETE → 같은 ViewSet
4. 일괄 삭제 → POST .../bulk-delete/ {ids:[1,2,3]}
```

### 2.2 가스 센서 등록 (Inspection 포함)
```
1. /admin-panel/gas-sensors/ → gas_sensor.js
2. GET /api/gas-sensors/next-code/ → 다음 사용 가능한 device_id 추천
3. POST /api/gas-sensors/check-connection/ → 실 장비 ping
4. POST /api/gas-sensors/ {device_id, threshold..., facility_id}
5. 검사 기록 → GET /api/gas-sensors/<id>/inspections/, POST .../inspections/<id>/action/
   (검사 일정·결과·재검사 지시)
```

### 2.3 맵 에디터 (지도 위 객체 배치)
```
1. /admin-panel/map-editor/ → map_editor.js (캔버스/SVG 기반)
2. GET /api/map-editor/objects/ → 모든 facility/equipment/sensor/device 좌표
3. JS에서 드래그앤드롭 → 변경 사항 누적
4. POST /api/map-editor/save/ {objects:[{id, type, x, y}, ...]}
   → 일괄 좌표 업데이트
```

## 3. 백엔드 소견

### 3.1 일반 코드 리뷰
- **[상] facility_admin.py 668줄, gas/power 각 485/453줄**
  단일 파일에 시설·설비·전력장치 CRUD가 함께 있고 helper도 모듈 레벨 (`_LIST_QUERY_PARAMS`, `_bulk_delete_request/response`). 도메인별 분리 시급:
  - `views/facility/{list.py, detail.py, bulk.py, select.py}`
  - `views/equipment/...`
  - `views/devices/{gas_sensor, power_device}/...`
- **[상] view에서 직접 ORM 호출 (selector 무시)**
  [facility_admin.py:91-118](../../../../drf-server/apps/facilities/views/facility_admin.py#L91-L118) `Facility.objects.all().prefetch_related().select_related()` + 필터 인라인. selectors/admin_devices.py가 존재하는데 활용 안 됨.
- **[중] 검색 파싱 로직이 view에**
  [facility_admin.py:97-104](../../../../drf-server/apps/facilities/views/facility_admin.py#L97-L104) `q.upper().startswith("FAC-")` 같은 도메인 규칙이 view에. selector 또는 utils로 추출.
- **[중] order 화이트리스트가 view에**
  [facility_admin.py:115-117](../../../../drf-server/apps/facilities/views/facility_admin.py#L115-L117) `if order not in [...]: order = "-created_at"` 인라인. 같은 패턴이 다른 view에도 반복 가능 — `OrderingFilter` 또는 헬퍼.
- **[중] inline_serializer 헬퍼 함수**
  [facility_admin.py:59-67](../../../../drf-server/apps/facilities/views/facility_admin.py#L59-L67) `_bulk_delete_request/response` 헬퍼. 다른 도메인(02 조직, 06 모니터링)에도 같은 패턴이 별도 구현되어 있을 가능성 — `apps/core/schemas.py::bulk_delete_schemas()` 단일화.
- **[중] 페이지뷰가 facility_admin.py 내부에**
  [FacilityAdminPageView (TemplateView)](../../../../drf-server/apps/facilities/views/facility_admin.py#L38)이 API view들과 같은 파일. 페이지/API 분리 권장 — `views/pages.py` vs `views/api/...`.

### 3.2 아키텍처/레이어
- **[참고] selectors/services 폴더는 정의되어 있음**
  `selectors/admin_devices.py`, `selectors/active_devices.py`, `services/device_service.py`, `services/threshold_service.py`. 그러나 view들이 활용을 안 하는 경향. 활용 패턴이 정착되지 않음.
- **[중] 검사(inspection) 워크플로의 service 위임 여부**
  Inspection 일정/결과/재검사 지시는 도메인 규칙이 복잡할 가능성 — `services/inspection_service.py`로 위임 필요. 현재 view에 인라인이면 추출 권장.
- **[중] 컨트롤러 패턴 부재로 인한 중복**
  Facility / Equipment / GasSensor / PowerDevice 모두 거의 동일한 CRUD/bulk-delete/select 패턴. ModelViewSet + 도메인별 mixin으로 압축 가능. 단, drf-spectacular 스키마 명시는 ViewSet에서 좀 까다로움 → 트레이드오프.

### 3.3 보안 관점 (요약)
- **[중] check-connection 엔드포인트의 SSRF 가능성**
  POST /api/gas-sensors/check-connection/, /api/power-devices/check-connection/. 사용자 입력 device 주소로 ping/HTTP 호출하면 SSRF(서버가 내부 망 임의 호스트로 요청). 코드 확인 후 IP 화이트리스트·private network 차단 필요.
- **[중] map-editor/save의 bulk 좌표 업데이트 트랜잭션**
  POST /api/map-editor/save/ 가 N개 객체 좌표를 한 번에 변경. 부분 실패 시 일부만 적용 → 지도 깨짐. `@transaction.atomic` 필수.
- **[하] FAC- 코드 prefix 가정**
  사용자가 입력한 q를 `int(q[4:])`로 파싱 → 잘못된 입력은 `qs.none()`으로 안전. 정상.

## 4. 프론트엔드(JS/HTML) 소견

### 4.1 백엔드 contract 정합성
- **[중] 4개 도메인 페이지가 거의 동일한 admin 패턴 (목록/필터/모달/일괄삭제)**
  facility.js, gas_sensor.js, power_system.js가 90% 동일한 구조 + 필드만 다름. **공통 base** 부재 — 같은 버그가 4곳에 복제 가능. `shared/admin-list-page.js::createListPage({fetchUrl, columns, modal, ...})` 추출 권장.

### 4.2 map_editor.js
- **[중] 캔버스 좌표 ↔ 백엔드 좌표 변환 일관성**
  지도 좌표계(픽셀 vs 정규화 0~1 vs 실제 미터)가 어디에서 변환되는지 명확해야 함. 변환 로직이 JS에만 있다면 다른 페이지(monitoring_workers의 작업자 위치)와 어긋날 수 있음. 변환 함수 단일화 필요.
- **[중] save 일괄 업로드의 부분 실패 노출**
  [map_editor 저장 시 일부 객체만 갱신 실패](../../../../drf-server/static/js/admin/map_editor/map_editor.js) 시 사용자에게 어떤 객체가 실패했는지 노출 필요. 현재 응답 형식 확인 필요.

### 4.3 페이지 셸 + 데이터 분리
- **[참고] facility.html 등 페이지는 셸만 + JS가 데이터 fetch — 좋은 패턴**
  서버 사이드 렌더링과 클라이언트 사이드 렌더링이 명확히 분리. 다만 페이지 진입 시 JS가 인증 체크 → 401 → 로그인 리다이렉트 흐름 일관성 필요(03 도메인 C4와 같은 이슈).

## 5. 개선 제안

### E1. facility_admin.py 668줄 분리 (시급) [상 · 대]
- **왜 필요?**: 단일 파일에 4개 도메인(시설/설비/전력장치 일부/맵에디터 헬퍼) 혼재. git 충돌·머지 리뷰·테스트 모두 어려움.
- **장점**: 도메인별 격리·테스트 1:1 매핑·신규 작업자 진입 장벽 낮음.
- **단점**: import 경로 변경 (모든 사용처 갱신).
- **변경 위치**: `views/facility/`, `views/equipment/`, `views/page_views.py` 분리 후 `views/__init__.py` re-export.

### E2. gas_sensor_admin.py / power_device_admin.py 분리 [상 · 중]
- **왜 필요?**: 각 485/453줄. 검사·CRUD·옵션 조회·연결 검증·코드 추천이 한 파일.
- **장점**: 동일 패턴 (점검·CRUD·옵션) 분리로 유지보수 명확.
- **단점**: 위와 동일.
- **변경 위치**: 각각 `views/gas_sensor/{crud, inspection, connection, codes}.py`, `views/power_device/{...}`.

### E3. selectors/services 활용 정착 [상 · 대]
- **왜 필요?**: 정의된 selectors/services를 view가 거의 안 씀. 같은 쿼리·필터가 여러 view에 반복.
- **장점**: 정책 변경 1곳 / 테스트 격리 / view 30~50줄로 축소.
- **단점**: 작업량. 도메인별로 PR 쪼개기 권장.
- **변경 위치**: 모든 facility/* view → selectors/admin_devices.py, services/device_service.py 위임.

### E4. check-connection SSRF 차단 [상 · 소]
- **왜 필요?**: 사용자 입력으로 임의 호스트에 요청. 내부 메타데이터 서비스(AWS 169.254.169.254 등) 접근 가능성.
- **장점**: 보안 사고 차단.
- **단점**: 합법적 IoT 장비 IP가 사설망에 있다면 화이트리스트 정책 필요.
- **변경 위치**: `services/device_service.py::check_connection(addr)` 진입에 IP/host 검증. private network 허용 정책을 settings에 명시.

### E5. map-editor/save 트랜잭션 [상 · 소]
- **왜 필요?**: 부분 실패 시 지도 좌표 깨짐.
- **장점**: 데이터 정합성.
- **단점**: 길어진 트랜잭션 — 좌표 변경은 빠르므로 영향 미미.
- **변경 위치**: [map_editor.py](../../../../drf-server/apps/facilities/views/map_editor.py) `MapEditorSaveView.post`에 `@transaction.atomic` + 객체별 응답 (성공/실패).

### E6. 검색·정렬 헬퍼 단일화 [중 · 중]
- **왜 필요?**: order 화이트리스트, q 파싱 패턴이 여러 view에 반복.
- **장점**: 한 곳 / DRF SearchFilter / OrderingFilter 활용.
- **단점**: drf-spectacular 스키마 어노테이션 보완 필요.
- **변경 위치**: 각 view에 `filter_backends = [SearchFilter, OrderingFilter]` + `search_fields`/`ordering_fields` 명시. 또는 `apps/core/filters.py` 헬퍼.

### E7. inline_serializer 헬퍼 통합 [중 · 소]
- **왜 필요?**: bulk-delete request/response 패턴이 여러 도메인에 분산.
- **변경 위치**: [apps/core/schemas.py](../../../../drf-server/apps/core/) 신규 — `bulk_delete_request_schema(name)`, `bulk_delete_response_schema(name)`.

### E8. 페이지뷰/API 분리 [중 · 소]
- **왜 필요?**: TemplateView와 APIView가 같은 파일에 있어 import 검색 시 노이즈.
- **변경 위치**: `views/page_views.py`로 모든 TemplateView 통합.

### E9. JS admin-list-page 베이스 [중 · 중]
- **왜 필요?**: 4개 admin 페이지가 90% 동일 구조. 같은 버그가 4곳에 복제될 위험.
- **장점**: 새 도메인 추가 시 100줄로 페이지 완성 / 버그 수정 1곳.
- **단점**: 템플릿화의 학습 비용. 일부 도메인 특수 요구가 깨끗하게 안 들어맞을 수 있음.
- **변경 위치**: [shared/admin-list-page.js](../../../../drf-server/static/js/shared/) 신규.

### E10. 좌표 변환 함수 단일화 [중 · 소]
- **왜 필요?**: map_editor와 monitoring_workers가 동일 좌표계를 다루는데 변환 로직이 분산되면 어긋남.
- **변경 위치**: [shared/coordinate.js](../../../../drf-server/static/js/shared/) 신규 — `pixelToNormalized`, `normalizedToFacilityMeter` 등.

## 6. 구현 추천 순서

### 1단계 — 보안·정합성 (즉시) ⚡
- **E4** check-connection SSRF 차단
- **E5** map-editor/save 트랜잭션
- **이유**: 보안 + 데이터 정합성 직결. 변경 작은데 효과 큼.

### 2단계 — 파일 분리 (1~2주) 🏗
- **E1** facility_admin.py 분리 (가장 큰 668줄 우선)
- **E2** gas/power_device_admin 분리
- **E8** 페이지뷰 분리 (E1·E2와 함께)
- **이유**: 분리 자체가 회귀 위험 낮은 작업이라 시급한 보안과 평행 진행 가능.

### 3단계 — selectors/services 활용 정착 (다음 sprint) 🧱
- **E3** view → selector/service 위임 (도메인별 PR 쪼개기)
- **E6** 검색·정렬 헬퍼
- **E7** inline_serializer 통합
- **이유**: 컨벤션 정합. E1·E2 분리 후 개별 파일이 작아진 상태에서 진행.

### 4단계 — JS 공통화 (여유 시) ✨
- **E9** admin-list-page 베이스
- **E10** 좌표 변환 단일화

### ⚠️ 주의사항 (초보자용)
- **E1·E2 분리는 git mv 활용**: 단순 복사 후 삭제하면 git이 새 파일로 인식 → blame/log 추적 불가. `git mv`로 이동 후 분할.
- **E3은 PR을 도메인별로 쪼개기**: 시설→설비→가스센서→전력장치 순서. 각 PR이 독립적으로 통과해야 회귀 격리 가능.
- **E4 SSRF 차단 시 IoT 장비 통신이 막힐 수 있음**: 운영 IoT 장비 IP 대역을 사전 파악 후 화이트리스트 구성. 갑작스러운 차단은 운영 사고로 이어짐.
- **E9 베이스 추출은 템플릿 메서드 패턴 vs 컴포지션 신중 선택**: 너무 많은 hook을 두면 새 페이지 추가 시 학습 비용 증가. 단순 fetch + render만 베이스에 두고 나머지는 자유도 부여 권장.
