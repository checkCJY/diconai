# 07. 지오펜스·작업자 위치 (Geofence · Positioning · IoT WS)

## 1. 범위

### 1.1 API/WS 엔드포인트
| 서버 | URL | 메서드 | 핸들러 | 권한 |
|---|---|---|---|---|
| **drf** | `/api/geofences/` | GET, POST | GeoFenceViewSet | IsAuthenticated |
| **drf** | `/api/geofences/<id>/` | GET, PUT, DELETE | GeoFenceViewSet | IsAuthenticated |
| **drf** | `/api/admin/geofences/` | GET | GeoFenceAdminListView | IsSuperAdmin |
| **drf** | `/api/admin/geofences/<id>/` | GET | GeoFenceAdminDetailView | IsSuperAdmin |
| **drf** | `/api/positioning/receive/` | POST | WorkerPositionReceiveView | **AllowAny** |
| **fastapi** | `/api/positioning/receive` | POST | receive_positions (HTTP) | (무인증) |
| **fastapi** | `/ws/position/` | WS | position_stream (IoT 수신) | **무인증** |
| **fastapi** | `/ws/positions/` | WS | (브라우저 송신, 1초 주기) | (무인증) |

### 1.2 백엔드 파일
- **drf 지오펜스**:
  - [drf-server/apps/geofence/views/admin_views.py](../../../drf-server/apps/geofence/views/admin_views.py) — 154줄
  - [drf-server/apps/geofence/views/geofence_views.py](../../../drf-server/apps/geofence/views/geofence_views.py) — 150줄
  - [drf-server/apps/geofence/selectors/geofence_candidates.py](../../../drf-server/apps/geofence/selectors/geofence_candidates.py)
  - [drf-server/apps/geofence/services/geofence_service.py](../../../drf-server/apps/geofence/services/geofence_service.py)
  - [drf-server/apps/geofence/models/](../../../drf-server/apps/geofence/models/) — GeoFence
- **drf 포지셔닝**:
  - [drf-server/apps/positioning/views/position_views.py](../../../drf-server/apps/positioning/views/position_views.py) — 112줄
  - [drf-server/apps/positioning/services/position_service.py](../../../drf-server/apps/positioning/services/position_service.py) — **217줄** (handle_position_receive)
  - [drf-server/apps/positioning/serializers/serializers.py](../../../drf-server/apps/positioning/serializers/serializers.py)
  - [drf-server/apps/positioning/models/worker_position.py](../../../drf-server/apps/positioning/models/worker_position.py)
- **fastapi 위치 WS**:
  - [fastapi-server/websocket/routers/ws_router.py:135-180](../../../fastapi-server/websocket/routers/ws_router.py#L135-L180) — IoT 수신
  - [fastapi-server/websocket/routers/ws_router.py:111-132](../../../fastapi-server/websocket/routers/ws_router.py#L111-L132) — worker_stream (개인 알림)
  - [fastapi-server/services/positioning/](../../../fastapi-server/) — receive_positions (HTTP)

### 1.3 프론트엔드 파일
- 지오펜스 관리:
  - [drf-server/static/js/admin/geofence/geofence.js](../../../drf-server/static/js/admin/geofence/geofence.js)
  - [drf-server/templates/admin_panel/geofence/geofence_list.html](../../../drf-server/templates/admin_panel/geofence/geofence_list.html)
  - [drf-server/templates/components/geofence_modal.html](../../../drf-server/templates/components/geofence_modal.html)
- 작업자 위치:
  - [drf-server/static/js/detail/monitoring_workers.js](../../../drf-server/static/js/detail/monitoring_workers.js)
  - [drf-server/static/js/detail/map_detail.js](../../../drf-server/static/js/detail/map_detail.js)
  - [drf-server/static/js/dashboard/panels/map-panel.js](../../../drf-server/static/js/dashboard/panels/map-panel.js)
- 작업자 개인 알림:
  - [drf-server/static/js/shared/worker-ws.js](../../../drf-server/static/js/shared/worker-ws.js)

## 2. 기능 흐름

### 2.1 IoT 위치 장비 → 브라우저 (실시간 위치)
```
경로 1 (HTTP): IoT → fastapi /api/positioning/receive (HTTP) → fastapi receive_positions
경로 2 (WS):   IoT → fastapi /ws/position/ → position_stream

[fastapi → DRF]
1. fastapi가 worker 위치 수신 → 검증 → DRF로 비동기 POST
2. POST http://drf:8000/api/positioning/receive/  body=[{worker_id, facility_id, x, y, measured_at}, ...]
3. WorkerPositionReceiveView.post:
   ├─ 배열 검증 (isinstance list)
   ├─ WorkerPositionReceiveSerializer(many=True).is_valid
   ├─ for item: handle_position_receive(...) ← service 위임 (좋음)
   │   └─ position_service.py: 위치 저장 + zone 진입 판정 + 위험도 계산
   └─ 응답 {saved, ids, statuses[{worker_id, risk_level, zone_name}]}

[브라우저 broadcast]
4. fastapi의 worker_positions 공유 상태 갱신 (state.py)
5. broadcast_loop이 1초 주기로 build_broadcast_payload() → /ws/sensors/에 송신
6. monitoring_workers.js / map_detail.js / dashboard map-panel.js → 점 위치 갱신
```

### 2.2 지오펜스 진입 알람 (개인 알림)
```
1. IoT 위치 → fastapi → DRF position 저장 (위 2.1)
2. position_service.handle_position_receive 내부:
   ├─ 작업자 facility의 활성 GeoFence 조회 (selectors/geofence_candidates.py)
   ├─ point-in-polygon 판정 (services/geofence_service.py)
   └─ 진입 판정 시 → Celery 알람 태스크 → POST /internal/alarms/push/ (worker_id 포함)
3. fastapi alarm_router (04 도메인):
   ├─ active_alarms.append(payload)
   └─ if alarm_type=="geofence_intrusion" and worker_id:
       worker_clients[user_id].send_json({type:"worker_alert", ...})
4. 브라우저 worker-ws.js (작업자 개인 디바이스):
   └─ /ws/worker/{user_id}/ 연결 → 개인 알림 수신 → 모달/팝업
```

### 2.3 지오펜스 정의 관리
```
1. /admin-panel/geofence/ → geofence.js
2. GET /api/admin/geofences/ → 목록
3. POST /api/geofences/ {name, polygon[(x,y)...], facility_id, danger_level} → 신규
4. PUT/DELETE /api/geofences/<id>/
5. 지도 위에 polygon 그리기 → 좌표 정규화 → 저장
```

## 3. 백엔드 소견

### 3.1 일반 코드 리뷰
- **[상] 컨벤션 위반: print() 사용**
  [position_views.py:102](../../../drf-server/apps/positioning/views/position_views.py#L102) `print(f"[positioning] 저장 오류: {e}")`. CLAUDE.md "print() 금지 → logging 사용". 운영 환경에선 stdout으로 새고 표준 로그 시스템에 안 잡힘. **`logger.exception(...)`로 변경 시급**.
- **[중] bare except Exception**
  [position_views.py:101-102](../../../drf-server/apps/positioning/views/position_views.py#L101-L102) `except Exception as e: print(...)`. 모든 예외를 묻고 다음 항목으로 진행. 부분 실패가 silent — 적어도 위에서 본 부분 실패 응답 패턴(B7) 적용 권장.
- **[중] for-loop service 호출 → 트랜잭션 부재**
  [position_views.py:81-100](../../../drf-server/apps/positioning/views/position_views.py#L81-L100) 100명 위치 한 번에 받아 1명씩 service 호출 + DB 저장. 중간 실패 시 일부만 저장 + 응답엔 부분 결과. `@transaction.atomic` + `bulk_create`로 1쿼리 처리 권장 (지오펜스 판정은 분기 로직이라 일괄 처리 어려울 수 있음 — 트레이드오프).
- **[중] geofence/views/admin_views.py:61-75 view에서 직접 ORM (사전 진단)**
  selectors/geofence_candidates.py 존재하는데 view가 직접 GeoFence.objects.filter 조회. selectors 활용 통일.
- **[하] handle_position_receive 시그니처 길음**
  [position_views.py:83-91](../../../drf-server/apps/positioning/views/position_views.py#L83-L91) 7개 인자 직접 전달. validated_data dict 그대로 전달하거나 dataclass 권장.

### 3.2 아키텍처/레이어
- **[참고] positioning은 service 활용 잘 됨**
  view가 거의 service 호출만. position_service.py 217줄에 비즈니스 로직 집중. **모범 사례**.
- **[참고] geofence도 selectors/services 폴더 존재**
  단, 활용은 일관되지 않음(view 직접 호출 사례 있음).
- **[중] HTTP /api/positioning/receive 와 WS /ws/position/ 두 경로**
  같은 데이터를 두 인입 경로로 받음. 운영상 어떤 장비가 어떤 경로를 쓰는지 명확해야 함. 한쪽 표준화 권장 또는 각 경로 사용 케이스를 [docs/specs/](../../../docs/specs/)에 명시.

### 3.3 보안 관점 (요약)
- **[상] /ws/worker/{user_id}/ 인증 부재 (04와 동일)**
  [ws_router.py:111-132](../../../fastapi-server/websocket/routers/ws_router.py#L111-L132) 임의 user_id로 접속 시 다른 사용자의 개인 알림을 가로챌 수 있음. 해당 사용자가 위험 영역 진입 사실이 제3자에게 누출. JWT 검증 시급.
- **[상] /ws/position/ 무인증 (IoT 장비 위치 위변조)**
  [ws_router.py:135-180](../../../fastapi-server/websocket/routers/ws_router.py#L135-L180) IoT 장비 인증이 전혀 없음. 외부에서 임의 worker_id의 가짜 위치를 주입 가능 → 작업자가 위험 영역 안에 있는데도 안전 영역으로 위변조하면 알람 미발생. **장비 인증 시급**.
- **[상] /api/positioning/receive AllowAny**
  [position_views.py:30](../../../drf-server/apps/positioning/views/position_views.py#L30) 인입 ingest와 동일 이슈 (06의 F1과 함께 해결).
- **[중] worker_positions dict 동시성 보호 부재 (09에서 종합)**
  [ws_router.py:168-173](../../../fastapi-server/websocket/routers/ws_router.py#L168-L173) `worker_positions[worker_id] = {...}` 직접 dict mutation. asyncio 단일 스레드라 동시 mutation 위험은 낮으나, 다중 워커(uvicorn) 배포 시 위험.

## 4. 프론트엔드(JS/HTML) 소견

### 4.1 백엔드 contract 정합성
- **[상] worker-ws.js의 user_id 자체 결정**
  [shared/worker-ws.js](../../../drf-server/static/js/shared/worker-ws.js)가 localStorage에서 user_id 읽어 `/ws/worker/${user_id}/` 연결. 클라이언트가 결정하는 user_id를 서버가 신뢰 → 사실상 인증 부재. 서버가 JWT에서 user_id 추출해 파라미터를 무시해야 안전.
- **[중] 좌표 정합성 (지도 좌표계)**
  geofence.js polygon 저장 좌표 vs monitoring_workers.js worker 점 좌표가 같은 좌표계여야 진입 판정 정확. 정규화 0~1 vs 픽셀 vs 미터의 변환 단일화 (E10과 동일 이슈).

### 4.2 JS 책임 분리
- **[중] 지도 렌더링 로직이 3곳에 분산**
  - dashboard/panels/map-panel.js (메인 대시보드 지도)
  - detail/map_detail.js (서브 페이지 지도)
  - admin/map_editor/map_editor.js (관리자 편집)
  - admin/geofence/geofence.js (지오펜스 그리기)
  4개가 다 같은 지도 + 다른 인터랙션. 공통 베이스 `shared/map-base.js` 추출 필요.

### 4.3 worker-ws.js 재연결
- **[중] WS disconnect 시 자동 재연결 정책**
  [shared/worker-ws.js](../../../drf-server/static/js/shared/worker-ws.js) 의 재연결 로직 확인 필요. IoT 장비/모바일 작업자는 네트워크 끊김 빈번. 끊김 시 재연결 + 재인증 + 누락 알람 catch-up이 필요. WSClient (shared/ws-client.js)와 일관되게.

## 5. 개선 제안

### G1. /ws/worker/{user_id}/ JWT 인증 [상 · 중]
- **왜 필요?**: 임의 user_id로 다른 사람의 위험 알림을 가로채는 정보 누출. 산업 안전 시스템에서 가장 큰 보안 이슈 중 하나.
- **장점**: 개인 알림 격리 / 정보 누출 차단.
- **단점**: WS 핸드셰이크에서 JWT 검증 필요(첫 메시지 또는 query string).
- **변경 위치**: [ws_router.py:111-132](../../../fastapi-server/websocket/routers/ws_router.py#L111-L132) 진입 시 JWT 검증 후 user_id 일치 확인. [shared/worker-ws.js](../../../drf-server/static/js/shared/worker-ws.js) 연결 시 토큰 동봉.

### G2. /ws/position/ IoT 장비 인증 [상 · 대]
- **왜 필요?**: 가짜 위치 주입은 실제 위험 상황을 은폐하거나 거짓 알람을 만드는 직접적 안전 사고 가능성. 산재 예방 시스템의 핵심 데이터.
- **장점**: 데이터 신뢰성 / 사고 시 책임 추적.
- **단점**: 장비 펌웨어 협업 필요 (06의 F2와 결합).
- **변경 위치**: [ws_router.py:135-180](../../../fastapi-server/websocket/routers/ws_router.py#L135-L180) 진입 시 device certificate/secret 검증. 장비 등록 절차(F2)와 함께 진행.

### G3. print() → logging [상 · 소]
- **왜 필요?**: 컨벤션 위반 + 운영 로그 누락.
- **장점**: 표준 로그 인프라 적용.
- **단점**: 없음.
- **변경 위치**: [position_views.py:102](../../../drf-server/apps/positioning/views/position_views.py#L102) `logger.exception(...)`. 다른 print 사용처 grep으로 일괄 검색.

### G4. 위치 receive 부분 실패 응답 [중 · 소]
- **왜 필요?**: 일부 위치 저장 실패 시 응답이 `saved=숫자`만 — 누가 실패했는지 알 수 없음.
- **장점**: 운영 가시성 / 디버깅 용이.
- **단점**: 응답 스키마 변경.
- **변경 위치**: [position_views.py:81-103](../../../drf-server/apps/positioning/views/position_views.py#L81-L103) `failed:[{worker_id, reason}]` 추가.

### G5. position_views 트랜잭션·bulk_create [중 · 중]
- **왜 필요?**: 100명 위치를 1명씩 INSERT — N+1 + 부분 실패 위험.
- **장점**: 성능 향상 (10배+) / 일관성.
- **단점**: handle_position_receive가 zone 진입 판정 등 분기 로직 포함이라 단순 bulk 어려움. 위치 저장과 zone 판정을 분리해 위치는 bulk, zone 판정은 별도 처리.
- **변경 위치**: [position_service.py](../../../drf-server/apps/positioning/services/position_service.py) — `bulk_save_positions(items)` + `evaluate_zones_async(items)` 분리.

### G6. geofence selectors 활용 [중 · 소]
- **왜 필요?**: selectors/geofence_candidates.py 존재하는데 view 직접 ORM (사전 진단).
- **장점**: 컨벤션 정합 / 정책 변경 1곳.
- **변경 위치**: [admin_views.py:61-75](../../../drf-server/apps/geofence/views/admin_views.py#L61-L75) selectors 위임.

### G7. 지도 렌더링 베이스 추출 [중 · 중]
- **왜 필요?**: 4개 JS 파일에 지도 로직 분산 → 좌표계·렌더 버그 4곳에 복제.
- **장점**: 한 곳 / 좌표 변환 단일화.
- **단점**: 학습 비용 / 4개 페이지 전부 갱신.
- **변경 위치**: [shared/map-base.js](../../../drf-server/static/js/shared/) 신규 — Canvas/SVG 렌더, 좌표 변환, 이벤트 위임.

### G8. WS 자동 재연결 표준화 [중 · 소]
- **왜 필요?**: 모바일/IoT 환경에서 끊김 빈번. 끊긴 동안 알람 누락 시 안전 사고.
- **장점**: 신뢰성 / 사용자 신뢰.
- **단점**: 재연결 시 누락 알람 catch-up은 서버 측 last-event-id 지원 필요.
- **변경 위치**: [shared/worker-ws.js, ws-client.js](../../../drf-server/static/js/shared/) 일관 적용. 서버는 `?last_event_id=N` 쿼리 지원.

### G9. handle_position_receive 인자 dataclass [하 · 소]
- **왜 필요?**: 7개 인자 직접 전달은 호출 시 가독성 저하.
- **변경 위치**: [position_service.py](../../../drf-server/apps/positioning/services/position_service.py) — `@dataclass class PositionReceivePayload`.

### G10. HTTP vs WS 인입 경로 정리 [하 · 중]
- **왜 필요?**: 같은 데이터의 두 경로 존재 → 운영 혼란.
- **변경 위치**: [docs/specs/](../../../docs/specs/) 문서화 또는 한쪽 deprecate. WS는 양방향·연결 유지가 필요한 케이스만, 단순 push는 HTTP가 무난.

## 6. 구현 추천 순서

### 1단계 — 보안·컨벤션 (즉시) ⚡
- **G3** print() → logging (라인 1개, 즉시)
- **G1** /ws/worker/{user_id}/ JWT (04의 D2와 동일 작업)
- **이유**: 컨벤션·정보 누출 직접 영향. G3는 거의 무비용, G1은 산업 안전 시스템에서 가장 큰 위험 중 하나.

### 2단계 — 정합성·UX (1~2주) 🔧
- **G4** 부분 실패 응답
- **G6** geofence selectors 활용
- **G8** WS 자동 재연결 표준화
- **이유**: 운영 가시성·신뢰성 향상. 변경 작은데 효과 큼.

### 3단계 — IoT 장비 인증 (장기) 🔐
- **G2** /ws/position/ 장비 인증 (펌웨어 협업, 06의 F2와 결합)
- **이유**: 산재 예방 시스템의 핵심 데이터 신뢰성. 큰 작업이지만 우선순위 최상위.

### 4단계 — 성능·아키텍처 (다음 sprint) 🏗
- **G5** 위치 bulk_create 분리
- **G7** 지도 렌더링 베이스 추출
- **이유**: 작업자 수가 많아질수록 영향. 현 시점에선 여유 있음.

### 5단계 — 클린업 (여유 시) 🧹
- **G9** dataclass
- **G10** HTTP vs WS 정리

### ⚠️ 주의사항 (초보자용)
- **G1·G2 보안 변경은 e2e 테스트(PR-H 4종) 회귀 필수**: 인증 강화로 알람 흐름 자체가 막힘 → 테스트 통과 확인 후 머지.
- **G2 IoT 장비 인증은 전체 운영 영향**: 단계적 — (1) 등록 안 된 장비도 일단 받되 로깅 → (2) 등록된 장비만 받기. 한 번에 전환하면 운영 중인 장비 모두 끊김.
- **G7 지도 베이스 추출은 PR을 페이지별로**: 한꺼번에 4페이지 갱신하면 회귀 어려움. base 도입 → page 1개씩 마이그레이션.
- **G5 bulk_create는 zone 판정과 분리 신중**: 분리 시 위치 저장과 알람 발생 순서가 어긋날 수 있음. 알람이 위치보다 먼저 도착해도 무방한지 확인.
