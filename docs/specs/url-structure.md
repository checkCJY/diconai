# URL 구조

> 기준일: 2026-05-19 / 브랜치: feature/power_zscore_cp

URL 분리 원칙:
- **페이지** (HTML): 루트 경로 (`/dashboard/...`, `/admin-panel/...`)
- **API** (JSON): `/api/` 프리픽스 필수 (`/api/auth/...`, `/api/admin/...`)
- **어드민 패널**: `/admin-panel/` 프리픽스 (Django Admin `/admin/` 과 별도)
- **내부 전용**: `/internal/` 또는 `/api/internal/` 프리픽스 (localhost / 서비스 토큰)
- **WebSocket**: `/ws/...` (FastAPI 전용)
- URL 경로: `kebab-case`, API 컬렉션은 복수형

---

## §1. drf-server (포트 8000)

### 1.1 페이지 (HTML 렌더링)

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
| GET | `/dashboard/monitoring/events/<event_id>/` | 이벤트 상세 |
| GET/POST | `/admin/` | Django Admin |
| GET | `/health/` | 헬스체크 (`{"status": "ok"}`) |
| GET | `/metrics` | Prometheus 메트릭 |

### 1.2 어드민 패널 페이지 (`/admin-panel/` 프리픽스)

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
| GET | `/admin-panel/safety/checklist/` | 작업 전 안전 점검 관리 (★ 신규) |
| GET | `/admin-panel/safety/vr-training/` | VR 교육 콘텐츠 관리 (★ 신규) |
| GET | `/admin-panel/notices/` | 공지사항 목록 (★ 신규) |
| GET | `/admin-panel/notices/create/` | 공지사항 등록 (★ 신규) |
| GET | `/admin-panel/notices/<pk>/` | 공지사항 상세 (★ 신규) |
| GET | `/admin-panel/notices/<pk>/edit/` | 공지사항 수정 (★ 신규) |
| GET | `/admin-panel/logs/system/` | 시스템 로그 (★ 신규) |
| GET | `/admin-panel/logs/activity/` | 사용자 활동 로그 (★ 신규) |
| GET | `/admin-panel/logs/integration/` | 통합 로그 (★ 신규) |
| GET | `/admin-panel/logs/map-edit/` | 지도 편집 로그 (★ 신규) |

### 1.3 인증 API (`/api/auth/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/auth/login/` | 로그인 (JWT 발급) |
| GET | `/api/auth/me/` | 내 정보 조회 |
| GET/PATCH | `/api/auth/profile/` | 내 프로필 조회·수정 |
| POST | `/api/auth/password/change/` | 비밀번호 변경 |
| POST | `/api/auth/logout/` | 로그아웃 |
| POST | `/api/auth/token/refresh/` | JWT 토큰 갱신 |

### 1.4 대시보드 API (`/dashboard/api/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/dashboard/api/menu/` | 사이드바 메뉴 구조 |
| GET | `/dashboard/api/safety-status/` | 내 안전 점검 현황 |
| GET | `/dashboard/api/safety-history/` | 안전 점검 이력 |
| GET | `/dashboard/api/workers-list/` | 작업자 목록 |
| GET | `/dashboard/api/refresh/` | 대시보드 갱신 데이터 |
| GET/POST | `/dashboard/api/vr-progress/` | VR 진행률 조회·저장 |
| GET | `/dashboard/api/vr-content/active/` | 현재 facility 활성 VR 콘텐츠 (★ 신규) |

### 1.5 알람·이벤트 API (`/alerts/api/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/alerts/api/my-status/` | 내 알람 현황 |
| GET | `/alerts/api/worker-summary/` | 작업자별 알람 요약 |
| POST | `/alerts/api/anomaly-alarm-records/` | AI 이상탐지 알람 생성 (FastAPI → DRF) (★ 신규) |
| GET/POST | `/alerts/api/alarms/` | AlarmRecord 목록·생성 |
| GET/PATCH/DELETE | `/alerts/api/alarms/<pk>/` | AlarmRecord 상세·수정·삭제 |
| GET | `/alerts/api/events/` | Event 목록 |
| GET | `/alerts/api/events/<pk>/` | Event 상세 |
| POST | `/alerts/api/events/<pk>/resolve/` | 이벤트 RESOLVED 처리 |

### 1.6 지오펜스 API (`/api/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET/POST | `/api/geofences/` | 지오펜스 목록·생성 |
| GET/PUT/PATCH/DELETE | `/api/geofences/<pk>/` | 지오펜스 상세·수정·삭제 |
| GET | `/api/admin/geofences/` | 관리자용 지오펜스 목록 |
| GET/PUT | `/api/admin/geofences/<pk>/` | 관리자용 지오펜스 상세 |

### 1.7 어드민 API — 사용자·조직 (`/api/admin/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/admin/accounts/` | 사용자 목록 (필터·페이지네이션) |
| GET/PATCH/DELETE | `/api/admin/accounts/<pk>/` | 사용자 상세·수정·삭제 |
| POST | `/api/admin/accounts/<pk>/<action>/` | 계정 잠금·해제 |
| GET | `/api/admin/organizations/tree/` | 조직 트리 |
| GET/POST | `/api/admin/departments/` | 부서 목록·생성 |
| GET/PATCH/DELETE | `/api/admin/departments/<pk>/` | 부서 상세·수정·삭제 |
| GET | `/api/admin/departments/<pk>/members/` | 부서원 목록 (`pk="none"`은 무소속) |
| POST | `/api/admin/departments/<pk>/members/add/` | 부서원 추가 |
| POST | `/api/admin/departments/<pk>/members/move/` | 부서원 이동 |
| POST | `/api/admin/departments/<pk>/members/remove/` | 부서원 제거 |
| POST | `/api/admin/departments/<pk>/members/assign-leader/` | 부서장 지정 |

### 1.8 어드민 API — 데이터 조회 (`/api/admin/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/admin/gas-data/` | 유해가스 데이터 목록 |
| GET | `/api/admin/gas-data/export/` | 유해가스 데이터 CSV 내보내기 |
| GET | `/api/admin/gas-data/sensors/` | 센서 드롭다운용 목록 |
| GET | `/api/admin/power-data/` | 전력 데이터 목록 |
| GET | `/api/admin/power-data/export/` | 전력 데이터 CSV 내보내기 |
| GET | `/api/admin/power-data/devices/` | 전력 장비 드롭다운용 목록 |

### 1.9 어드민 API — 안전 점검 (`/api/admin/safety/` 프리픽스) ★ 신규

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/admin/safety/checklist/state/` | 헤더 메타 (최근 반영일, 편집 중 여부) |
| GET/POST | `/api/admin/safety/sections/` | 섹션 목록·생성 |
| POST | `/api/admin/safety/sections/reorder/` | 섹션 순서 변경 |
| GET/PATCH/DELETE | `/api/admin/safety/sections/<pk>/` | 섹션 상세·수정·삭제 |
| POST | `/api/admin/safety/sections/<section_id>/items/` | 섹션 내 문항 생성 |
| POST | `/api/admin/safety/items/reorder/` | 문항 순서 변경 |
| GET/PATCH/DELETE | `/api/admin/safety/items/<pk>/` | 문항 상세·수정·삭제 |
| POST | `/api/admin/safety/items/<pk>/duplicate/` | 문항 복제 |
| POST | `/api/admin/safety/checklist/publish/` | 반영 저장 (Revision 스냅샷 발행) |
| GET | `/api/admin/safety/checklist/revisions/` | 반영 이력 목록 |
| GET | `/api/admin/safety/checklist/revisions/<pk>/` | 반영 이력 단건 |

### 1.10 운영자 안전 점검 API (`/api/safety/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/safety/checklist/active/` | 현재 활성 Revision 스냅샷 (현장 작업자용) |

### 1.11 어드민 API — VR 교육 (`/api/admin/training/` 프리픽스) ★ 신규

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/admin/training/vr-training/` | 현재 facility VR 콘텐츠 조회 |
| POST | `/api/admin/training/vr-training/replace/` | 콘텐츠 파일 교체 |
| GET/PATCH | `/api/admin/training/vr-training/<pk>/` | 메타 조회·수정 |
| GET | `/api/admin/training/vr-training/<pk>/revisions/` | 콘텐츠 변경 이력 |

### 1.12 공지사항 API (`/api/admin/` 프리픽스) ★ 신규

| Method | Path | 설명 |
|--------|------|------|
| GET/POST | `/api/admin/notices/` | 공지사항 목록·등록 |
| GET/PATCH/DELETE | `/api/admin/notices/<pk>/` | 공지사항 상세·수정·삭제 |
| POST | `/api/admin/notices/<pk>/attachments/` | 첨부파일 업로드 |
| DELETE | `/api/admin/notices/<pk>/attachments/<att_id>/` | 첨부파일 삭제 |

### 1.13 로그 관리 API (`/api/admin/` 프리픽스) ★ 신규

| Method | Path | 설명 | 출처 |
|--------|------|------|------|
| GET | `/api/admin/activity-logs/` | 사용자 활동 로그 | apps.core |
| GET | `/api/admin/map-edit-logs/` | 지도 편집 로그 (MAP_ action만) | apps.core |
| GET | `/api/admin/system-logs/` | 시스템 애플리케이션 로그 | apps.operations |
| GET | `/api/admin/integration-logs/` | 통합/외부 호출 로그 | apps.operations |

### 1.14 ML API (`/api/ml/` 프리픽스) ★ 신규

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/ml/models/active/` | 활성 MLModel 메타 (sensor_type, algorithm, sensor_identifier 3축 매칭) |
| POST | `/api/ml/anomaly-results/` | MLAnomalyResult 생성 (FastAPI 추론 결과 영속화) |

### 1.15 센서 데이터 수신 API (FastAPI → DRF 내부 통신)

| Method | Path | 호출 주체 | 설명 |
|--------|------|----------|------|
| POST | `/api/monitoring/gas/` | FastAPI gas_service | 가스 측정값 저장 |
| GET | `/api/monitoring/power/thresholds/` | FastAPI | 전력 임계치 조회 |
| POST | `/api/monitoring/power/channel-meta/` | FastAPI channel_meta_cache | 채널 메타 동기화 (★ 신규) |
| POST | `/api/monitoring/power/event/` | FastAPI power_service | 전력 ON/OFF 스냅샷 저장 |
| POST | `/api/monitoring/power/data/` | FastAPI power_service | 전력 측정값 저장 |
| POST | `/api/positioning/receive/` | FastAPI position_router | 작업자 위치 수신·저장 |
| POST | `/api/internal/integration-logs/` | FastAPI | 통합 로그 적재 (★ 신규) |

### 1.16 설비·장치 관리 API (`/api/` 프리픽스)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/map-editor/objects/` | 지도 편집 오브젝트 조회 |
| POST | `/api/map-editor/save/` | 지도 편집 저장 |
| GET/POST | `/api/facilities/` | 공장 목록·생성 |
| GET/PATCH/DELETE | `/api/facilities/<pk>/` | 공장 상세·수정·삭제 |
| POST | `/api/facilities/bulk-delete/` | 공장 일괄 삭제 |
| GET | `/api/facilities/select/` | 공장 드롭다운용 목록 |
| GET | `/api/facilities/power-device-options/` | 공장 등록 시 전력 장치 옵션 |
| GET | `/api/facilities/devices/select/` | 미연결 전력 장치 드롭다운 |
| GET/POST | `/api/equipments/` | 설비(Equipment) 목록·생성 (★ 신규) |
| GET/PATCH/DELETE | `/api/equipments/<pk>/` | 설비 상세·수정·삭제 (★ 신규) |
| POST | `/api/equipments/bulk-delete/` | 설비 일괄 삭제 (★ 신규) |
| GET | `/api/gas-sensors/` | 유해가스 센서 목록 |
| GET/PATCH/DELETE | `/api/gas-sensors/<pk>/` | 센서 상세·수정·삭제 |
| POST | `/api/gas-sensors/bulk-delete/` | 센서 일괄 삭제 |
| GET | `/api/gas-sensors/next-code/` | 다음 센서 코드 자동 생성 |
| GET | `/api/gas-sensors/check-connection/` | 연결 상태 확인 |
| GET | `/api/gas-sensors/<sensor_pk>/inspections/` | 센서 점검 이력 |
| POST | `/api/gas-sensors/inspections/<inspection_pk>/action/` | 센서 점검 처리 |
| GET | `/api/power-devices/` | 전력 장치 목록 |
| GET/PATCH/DELETE | `/api/power-devices/<pk>/` | 전력 장치 상세·수정·삭제 |
| POST | `/api/power-devices/bulk-delete/` | 전력 장치 일괄 삭제 |
| GET | `/api/power-devices/codes/` | 전력 장치 코드 목록 |
| GET | `/api/power-devices/next-code/` | 다음 장치 코드 자동 생성 |
| GET | `/api/power-devices/check-connection/` | 연결 상태 확인 |
| GET | `/api/power-devices/<device_pk>/inspections/` | 장치 점검 이력 |
| POST | `/api/power-devices/inspections/<inspection_pk>/action/` | 장치 점검 처리 |
| GET | `/api/departments/select/` | 부서 드롭다운용 목록 |
| GET | `/api/managers/select/` | 관리자 드롭다운용 목록 |

### 1.17 OpenAPI / 스키마

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/schema/` | OpenAPI 스키마 (drf-spectacular) |
| GET | `/api/schema/swagger-ui/` | Swagger UI |
| GET | `/api/schema/redoc/` | ReDoc |

---

## §2. fastapi-server (포트 8001)

### 2.1 HTTP — 센서 데이터 수신

| Method | Path | 호출 주체 | 설명 |
|--------|------|----------|------|
| POST | `/api/sensors/info` | 가스 센서 장비 | 기기 정보 등록 (부팅 시 1회) |
| POST | `/api/sensors/gas` | 가스 센서 장비 | 가스 측정값 수신 → DRF 저장 + 공유 상태 갱신 + Z-score 발화 |
| POST | `/api/power/onoff` | 전력 센서 장비 | 16채널 ON/OFF 스냅샷 |
| POST | `/api/power/current` | 전력 센서 장비 | 16채널 전류(A) |
| POST | `/api/power/voltage` | 전력 센서 장비 | 16채널 전압(V) |
| POST | `/api/power/watt` | 전력 센서 장비 | 16채널 전력(W) — IF 추론 + 5축 정책 엔진 + 알람 발화 |
| POST | `/api/positioning/receive` | 더미 스크립트·IoT | 작업자 위치 배열 수신 |
| GET | `/health/` | 헬스 체크 | `{"status": "ok"}` |
| GET | `/metrics` | Prometheus | 메트릭 노출 |

### 2.2 AI 추론 API (`/ai/` 프리픽스) ★ 신규

| Method | Path | 설명 |
|--------|------|------|
| POST | `/ai/predict` | IF 이상탐지 추론 (sensor_type/sensor_identifier/window_values) |
| POST | `/ai/reload` | 모델 캐시 무효화 (sensor_type / algorithm / sensor_identifier 3축) |

캐시 키: `(sensor_type, algorithm, sensor_identifier)`. `algorithm` 은 `isolation_forest` 또는 `arima`. ARIMA 추론은 `_get_or_load_arima` 헬퍼 경유 (`/ai/predict` 는 IF 전용 — ARIMA 사용처는 power_service 내부에서 직접 호출).

### 2.3 내부 API (`/internal/` 프리픽스, localhost 전용)

| Method | Path | 호출 주체 | 설명 |
|--------|------|----------|------|
| POST | `/internal/alarms/push/` | DRF Celery | Redis 알람 큐(LPUSH) 추가 → alarm_flush_loop 즉시 소비 (★ Phase 1 C4) |
| GET | `/internal/scenario/mode` | 더미 polling | 현재 시나리오 모드 조회 |
| POST | `/internal/scenario/mode` | 운영자/대시보드 | 시나리오 모드 변경 |

`/internal/alarms/push/` 보안: `INTERNAL_SERVICE_TOKEN` 설정 시 Bearer 토큰 검증, 미설정 시 localhost(`127.0.0.1`/`::1`) 화이트리스트로 폴백.

시나리오 모드 (allowed):
- 공통: `mixed` / `normal` / `warning` / `danger`
- 전력 전용 (가스·위치는 `mixed` fallback): `overload` / `voltage_drop` / `phase_loss` / `degradation` / `night_abnormal` / `motor_stuck`
- 가스 전용 (전력·위치는 `mixed` fallback): `co_leak` / `h2s_leak` / `fire` / `chemical_spill`

### 2.4 WebSocket

| Path | 접속 주체 | 설명 |
|------|----------|------|
| `ws://localhost:8001/ws/sensors/` | 브라우저 | broadcast_loop 가 `BROADCAST_INTERVAL_SEC` 마다 통합 페이로드 송출 (가스+전력+위치). 별도 `alarm_flush_loop` 가 Redis 큐 pop 즉시 같은 채널로 알람 push |
| `ws://localhost:8001/ws/worker/{user_id}/` | 브라우저 (작업자) | 작업자 개인 알림 (지오펜스 진입 등 1:1 푸시) |
| `ws://localhost:8001/ws/position/` | IoT 위치 장비 | 위치 수신 → DRF 저장 + 공유 상태 갱신 |
| `ws://localhost:8001/ws/positions/` | 브라우저 | 1초마다 작업자 위치 배열 스트리밍 |

`/ws/sensors/`, `/ws/worker/{user_id}/`: `settings.JWT_SIGNING_KEY` 설정 시 query `?token=<access>` 로 JWT 검증 (옵트인, Phase 5). `/ws/worker/` 는 JWT payload 의 `user_id` 와 path `user_id` 일치까지 검증.
`/ws/position/`: 펌웨어 cert/secret 협업이 별도 sprint 라 무인증 유지.

---

## §3. 통합 흐름 요약

### 3.1 센서 데이터 흐름

```
[가스 센서 장비]
  POST :8001/api/sensors/gas
    └→ DRF POST :8000/api/monitoring/gas/  (DB 영속)
       + websocket/state.latest_gas_snapshot 갱신
       + Z-score 발화 시 Celery → /internal/alarms/push/

[전력 센서 장비]
  POST :8001/api/power/onoff
    └→ DRF POST :8000/api/monitoring/power/event/
  POST :8001/api/power/current|voltage|watt
    └→ DRF POST :8000/api/monitoring/power/data/
       + /api/power/watt 는 IF 추론 + 5축 정책 엔진 → /internal/alarms/push/ + /api/ml/anomaly-results/

[IoT 위치 장비 / 더미]
  POST :8001/api/positioning/receive     (HTTP)
  WS   :8001/ws/position/                (WebSocket)
    └→ DRF POST :8000/api/positioning/receive/

[채널 메타 동기화 (5분 주기, fastapi 내부 loop)]
  GET  :8000/api/admin/power-data/devices/ → channel_meta 캐시 갱신
```

### 3.2 알람 흐름 (Phase 1 C4 — Redis 큐 기반)

```
[가스/전력 임계 초과 또는 AI 이상탐지]
  DRF Celery task (apps/alerts/tasks.py / apps/ml/tasks/)
    └→ POST :8001/internal/alarms/push/   (localhost / Bearer 토큰)
        └→ Redis LPUSH diconai:ws:alarms
            └→ alarm_flush_loop BRPOP (즉시)
                └→ /ws/sensors/ broadcast (sensor_clients 전체)
                + alarm_type=geofence_intrusion 시
                  worker_clients[worker_id] 에 1:1 push (/ws/worker/{id}/)

[운영자가 알람 팝업 확인]
  POST :8000/alerts/api/events/<id>/resolve/
    └→ 같은 event_id 로 ANOMALY 알람 재push (event_resolved_at 박힘)
        → 클라가 팝업 닫고 "위험 해소" 토스트
```

### 3.3 브라우저 수신 채널

```
WS :8001/ws/sensors/   ← broadcast_loop (주기) + alarm_flush_loop (이벤트)
   payload: {
     gas: latest_gas_snapshot,
     power: power_latest,
     workers: worker_positions,
     alarms: [<single alarm from Redis pop>]  // alarm_flush 시점에만
   }

WS :8001/ws/positions/ ← 1초 주기 worker_positions 단독 송출
WS :8001/ws/worker/{user_id}/ ← 본인용 alarm 1:1 push (지오펜스 진입 등)
```

---

## §4. 공유 상태 (fastapi-server/websocket/state.py)

| 변수 | 갱신 주체 | 소비 주체 |
|------|----------|----------|
| `latest_gas_snapshot` | gas_service | broadcast.py (`/ws/sensors/`) |
| `power_latest` | power_service | broadcast.py |
| `worker_positions` | position_router(HTTP) · ws_router(`/ws/position/`) | broadcast.py · `/ws/positions/` |
| `sensor_clients` | ws_router(`/ws/sensors/`) | broadcast_loop · alarm_flush_loop |
| `worker_clients` | ws_router(`/ws/worker/`) | internal alarm_router (1:1 push) |
| `scenario_mode` | internal scenario_router | 모든 dummy 스크립트 polling |

알람 큐는 더 이상 프로세스 메모리(`active_alarms`)가 아니라 **Redis LIST `diconai:ws:alarms`** 로 외부화됨 (Phase 1 C4 — set/clear race 및 정상화 알림 silent drop 해결).
