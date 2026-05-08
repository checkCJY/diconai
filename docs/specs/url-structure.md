# URL 구조

> 기준일: 2026-05-07 / 브랜치: feature/project_4_refactoring_docstring

---

## drf-server (포트 8000)

### 페이지 (HTML 렌더링)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | `/dashboard/` 로 리다이렉트 |
| GET | `/accounts/login/` | 로그인 페이지 |
| GET | `/dashboard/` | 메인 대시보드 |
| GET | `/dashboard/profile/` | 내 정보 프로필 |
| GET | `/dashboard/safety/checklist/` | 안전 점검 체크리스트 |
| GET | `/dashboard/safety/history/` | 안전 점검 이력 |
| GET | `/dashboard/safety/vr/` | VR 안전 교육 |
| GET | `/dashboard/monitoring/realtime/` | 실시간 모니터링 |
| GET | `/dashboard/monitoring/gas/` | 가스 센서 현황 |
| GET | `/dashboard/monitoring/power/` | 전력 현황 |
| GET | `/dashboard/monitoring/workers/` | 작업자 위치 현황 |
| GET | `/dashboard/monitoring/events/` | 이벤트 현황 |
| GET | `/dashboard/monitoring/events/<id>/` | 이벤트 상세 |
| GET/POST | `/admin/` | Django Admin |

---

### 어드민 패널 페이지 (HTML, `/admin-panel/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/admin-panel/accounts-management/` | 사용자 관리 페이지 |
| GET | `/admin-panel/organizations/` | 조직 관리 페이지 |
| GET | `/admin-panel/geofence/` | 지오펜스 관리 페이지 |
| GET | `/admin-panel/map-editor/` | 지도 편집기 |
| GET | `/admin-panel/facility/` | 스마트 전력 장치 관리 페이지 |
| GET | `/admin-panel/gas-sensors/` | 유해가스 센서 관리 페이지 |
| GET | `/admin-panel/data/gas/` | 유해가스 데이터 관리 페이지 |
| GET | `/admin-panel/data/power/` | 전력 데이터 관리 페이지 |

---

### 인증 API (`/api/auth/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/auth/login/` | 로그인 (JWT 발급) |
| GET | `/api/auth/me/` | 내 정보 조회 |
| GET/PATCH | `/api/auth/profile/` | 내 프로필 조회·수정 |
| POST | `/api/auth/password/change/` | 비밀번호 변경 |
| POST | `/api/auth/logout/` | 로그아웃 |
| POST | `/api/auth/token/refresh/` | JWT 토큰 갱신 |

---

### 대시보드 API (`/dashboard/api/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/dashboard/api/menu/` | 사이드바 메뉴 구조 |
| GET | `/dashboard/api/safety-status/` | 안전 점검 현황 |
| GET | `/dashboard/api/safety-history/` | 안전 점검 이력 |
| GET | `/dashboard/api/workers-list/` | 작업자 목록 |
| GET | `/dashboard/api/refresh/` | 대시보드 갱신 데이터 |
| GET/POST | `/dashboard/api/vr-progress/` | VR 진행률 조회·저장 |

---

### 알람·이벤트 API (`/alerts/api/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/alerts/api/my-status/` | 내 알람 현황 |
| GET | `/alerts/api/worker-summary/` | 작업자별 알람 요약 |
| GET/POST | `/alerts/api/alarms/` | AlarmRecord 목록·생성 |
| GET/PATCH/DELETE | `/alerts/api/alarms/<id>/` | AlarmRecord 상세·수정·삭제 |
| GET | `/alerts/api/events/` | Event 목록 |
| GET | `/alerts/api/events/<id>/` | Event 상세 |
| POST | `/alerts/api/events/<id>/resolve/` | 이벤트 RESOLVED 처리 (알람 팝업 확인 시) |

---

### 지오펜스 API

| Method | Path | 설명 |
|--------|------|------|
| GET/POST | `/api/geofences/` | 지오펜스 목록·생성 |
| GET/PUT/PATCH/DELETE | `/api/geofences/<id>/` | 지오펜스 상세·수정·삭제 |
| GET | `/api/admin/geofences/` | 관리자용 지오펜스 목록 |
| GET/PUT | `/api/admin/geofences/<id>/` | 관리자용 지오펜스 상세 |

---

### 어드민 API — 사용자·조직 (`/api/admin/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/admin/accounts/` | 사용자 목록 (필터·페이지네이션) |
| GET/PATCH/DELETE | `/api/admin/accounts/<pk>/` | 사용자 상세·수정·삭제 |
| POST | `/api/admin/accounts/<pk>/<action>/` | 계정 잠금·해제 |
| GET | `/api/admin/organizations/tree/` | 조직 트리 |
| GET/POST | `/api/admin/departments/` | 부서 목록·생성 |
| GET/PATCH/DELETE | `/api/admin/departments/<pk>/` | 부서 상세·수정·삭제 |
| GET | `/api/admin/departments/<pk>/members/` | 부서원 목록 |
| POST | `/api/admin/departments/<pk>/members/add/` | 부서원 추가 |
| POST | `/api/admin/departments/<pk>/members/move/` | 부서원 이동 |
| POST | `/api/admin/departments/<pk>/members/remove/` | 부서원 제거 |
| POST | `/api/admin/departments/<pk>/members/assign-leader/` | 부서장 지정 |

---

### 어드민 API — 데이터 조회 (`/api/admin/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/admin/gas-data/` | 유해가스 데이터 목록 (필터·페이지네이션) |
| GET | `/api/admin/gas-data/export/` | 유해가스 데이터 CSV 내보내기 |
| GET | `/api/admin/gas-data/sensors/` | 센서 드롭다운용 목록 |
| GET | `/api/admin/power-data/` | 전력 데이터 목록 (필터·페이지네이션) |
| GET | `/api/admin/power-data/export/` | 전력 데이터 CSV 내보내기 |
| GET | `/api/admin/power-data/devices/` | 전력 장비 드롭다운용 목록 |

---

### 센서 데이터 수신 API (FastAPI → DRF 내부 통신)

| Method | Path | 호출 주체 | 설명 |
|--------|------|----------|------|
| POST | `/api/monitoring/gas/` | FastAPI gas_service | 가스 측정값 저장 |
| GET | `/api/monitoring/power/thresholds/` | FastAPI | 전력 임계치 조회 |
| POST | `/api/monitoring/power/event/` | FastAPI power_service | 전력 ON/OFF 스냅샷 저장 |
| POST | `/api/monitoring/power/data/` | FastAPI power_service | 전력 측정값 저장 |
| POST | `/api/positioning/receive/` | FastAPI position_router | 작업자 위치 수신·저장 |

---

### 설비·장치 관리 API (`/api/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/map-editor/objects/` | 지도 편집 오브젝트 조회 |
| POST | `/api/map-editor/save/` | 지도 편집 저장 |
| GET/POST | `/api/facilities/` | 공장 목록·생성 |
| GET/PATCH/DELETE | `/api/facilities/<pk>/` | 공장 상세·수정·삭제 |
| POST | `/api/facilities/bulk-delete/` | 공장 일괄 삭제 |
| GET | `/api/facilities/select/` | 공장 드롭다운용 목록 |
| GET | `/api/facilities/power-device-options/` | 전력 장치 옵션 |
| GET | `/api/facilities/devices/select/` | 미연결 전력 장치 드롭다운 |
| GET/POST | `/api/equipments/` | 설비 목록·생성 |
| GET/PATCH/DELETE | `/api/equipments/<pk>/` | 설비 상세·수정·삭제 |
| POST | `/api/equipments/bulk-delete/` | 설비 일괄 삭제 |
| GET | `/api/gas-sensors/` | 유해가스 센서 목록 |
| GET/PATCH/DELETE | `/api/gas-sensors/<pk>/` | 센서 상세·수정·삭제 |
| POST | `/api/gas-sensors/bulk-delete/` | 센서 일괄 삭제 |
| GET | `/api/gas-sensors/next-code/` | 다음 센서 코드 자동 생성 |
| GET | `/api/gas-sensors/check-connection/` | 연결 상태 확인 |
| GET | `/api/gas-sensors/<sensor_pk>/inspections/` | 센서 점검 이력 |
| POST | `/api/gas-sensors/inspections/<pk>/action/` | 센서 점검 처리 |
| GET | `/api/power-devices/` | 전력 장치 목록 |
| GET/PATCH/DELETE | `/api/power-devices/<pk>/` | 전력 장치 상세·수정·삭제 |
| POST | `/api/power-devices/bulk-delete/` | 전력 장치 일괄 삭제 |
| GET | `/api/power-devices/codes/` | 전력 장치 코드 목록 |
| GET | `/api/power-devices/next-code/` | 다음 장치 코드 자동 생성 |
| GET | `/api/power-devices/check-connection/` | 연결 상태 확인 |
| GET | `/api/power-devices/<device_pk>/inspections/` | 장치 점검 이력 |
| POST | `/api/power-devices/inspections/<pk>/action/` | 장치 점검 처리 |
| GET | `/api/departments/select/` | 부서 드롭다운용 목록 |
| GET | `/api/managers/select/` | 관리자 드롭다운용 목록 |

---

## fastapi-server (포트 8001)

### HTTP — 센서 데이터 수신

| Method | Path | 호출 주체 | 설명 |
|--------|------|----------|------|
| POST | `/api/sensors/info` | 가스 센서 장비 | 기기 정보 등록 (부팅 시 1회) |
| POST | `/api/sensors/gas` | 가스 센서 장비 | 가스 측정값 수신 → DRF 저장 + 공유 상태 갱신 |
| POST | `/api/power/onoff` | 전력 센서 장비 | ON/OFF 상태 수신 |
| POST | `/api/power/current` | 전력 센서 장비 | 전류 수신 |
| POST | `/api/power/voltage` | 전력 센서 장비 | 전압 수신 |
| POST | `/api/power/watt` | 전력 센서 장비 | 전력(W) 수신 |
| POST | `/api/positioning/receive` | 더미 스크립트·IoT | 작업자 위치 배열 수신 → 공유 상태 갱신 + DRF 저장 |
| POST | `/internal/alarms/push/` | Celery (localhost) | 알람 큐에 추가 → 다음 WS 틱에 브라우저 전달 |
| GET | `/internal/scenario/mode` | 운영자 (localhost) | 현재 시나리오 모드 조회 |
| POST | `/internal/scenario/mode` | 운영자 (localhost) | 시나리오 모드 변경 (데모 제어) |
| GET | `/health/` | 헬스 체크 | `{"status": "ok"}` |

---

### WebSocket

| Path | 접속 주체 | 설명 |
|------|----------|------|
| `ws://localhost:8001/ws/sensors/` | 브라우저 | 5초마다 통합 페이로드 송출 (가스+전력+알람+작업자 위치) |
| `ws://localhost:8001/ws/worker/{user_id}/` | 브라우저 (작업자) | 작업자 개인 알림 전용 (1:1 푸시) |
| `ws://localhost:8001/ws/position/` | IoT 위치 장비 | 위치 수신 → DRF 저장 + 공유 상태 갱신 |
| `ws://localhost:8001/ws/positions/` | 브라우저 | 1초마다 작업자 위치 배열 스트리밍 |

---

## FastAPI → DRF 호출 흐름 요약

```
[가스 센서 장비]
  POST :8001/api/sensors/gas
    └→ DRF POST :8000/api/monitoring/gas/

[전력 센서 장비]
  POST :8001/api/power/onoff
    └→ DRF POST :8000/api/monitoring/power/event/
  POST :8001/api/power/current|voltage|watt
    └→ DRF POST :8000/api/monitoring/power/data/

[IoT 위치 장비 또는 더미]
  POST :8001/api/positioning/receive  (HTTP)
  WS   :8001/ws/position/             (WebSocket)
    └→ DRF POST :8000/api/positioning/receive/

[Celery 태스크 (DRF 컨텍스트)]
  POST :8001/internal/alarms/push/    (localhost only)
    └→ FastAPI active_alarms 큐 추가
       → 다음 브로드캐스트 틱(5초)에 브라우저 전달

[브라우저]
  WS :8001/ws/sensors/
    ← 공유 상태(websocket/state.py) 기반 페이로드 (5초 주기)
       · latest_gas_snapshot   (gas_service 갱신)
       · active_alarms         (alarm_flush_loop에서 flush)
       · power_latest          (power_service 갱신)
       · worker_positions      (ws/position/ 수신 시 갱신)
```

---

## 공유 상태 (fastapi-server/websocket/state.py)

| 변수 | 갱신 주체 | 소비 주체 |
|------|----------|----------|
| `latest_gas_snapshot` | gas_service | broadcast.py (/ws/sensors/) |
| `active_alarms` | gas_service, internal alarm_router | broadcast.py (flush 후 clear) |
| `power_latest` | power_service | broadcast.py |
| `worker_positions` | ws_router (/ws/position/), position_router | broadcast.py (/ws/sensors/) |
| `sensor_clients` | ws_router (/ws/sensors/) | broadcast_loop |
| `worker_clients` | ws_router (/ws/position/) | alarm_router (개인 전송) |
