# URL 구조

> 기준일: 2026-04-25 / 브랜치: devleop
> Phase 3 리팩토링 완료 + Phase 4 P0·P1 수정 반영

---

## drf-server (포트 8000)

### 페이지 (HTML 렌더링)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | `/dashboard/` 로 리다이렉트 |
| GET | `/accounts/login/` | 로그인 페이지 |
| GET | `/dashboard/` | 메인 대시보드 |
| GET | `/dashboard/jhh/` | ⚠️ 구 대시보드 — Phase 4 삭제 예정 |
| GET | `/dashboard/safety/checklist/` | 안전 점검 체크리스트 |
| GET | `/dashboard/safety/history/` | 안전 점검 이력 |
| GET | `/dashboard/safety/vr/` | VR 안전 교육 |
| GET | `/dashboard/monitoring/realtime/` | 실시간 모니터링 |
| GET | `/dashboard/monitoring/gas/` | 가스 센서 현황 |
| GET | `/dashboard/monitoring/power/` | 전력 현황 |
| GET | `/dashboard/monitoring/workers/` | 작업자 위치 현황 |
| GET | `/dashboard/monitoring/events/` | 이벤트 현황 |
| GET | `/dashboard/admin/` | 관리자 페이지 (HTML) |
| GET | `/admin-panel/geofence/` | 지오펜스 관리 페이지 |
| GET/POST | `/admin/` | Django Admin |

---

### 인증 API

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/auth/login/` | 로그인 (JWT 발급) |
| GET | `/api/auth/me/` | 내 정보 조회 |
| POST | `/api/auth/logout/` | 로그아웃 |
| POST | `/api/auth/token/refresh/` | JWT 토큰 갱신 |

---

### 대시보드 API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/dashboard/api/menu/` | 사이드바 메뉴 구조 반환 |
| GET | `/dashboard/api/safety-status/` | 안전 점검 현황 |
| GET | `/dashboard/api/refresh/` | 대시보드 갱신 데이터 |
| POST | `/dashboard/api/vr-progress/` | VR 진행률 저장 |

---

### 알람·이벤트 API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/alerts/api/` | 알람 목록 조회 (AlarmRecord) |
| POST | `/alerts/api/` | 알람 생성 |
| GET | `/alerts/api/{id}/` | 알람 상세 |
| PATCH | `/alerts/api/{id}/` | 알람 수정 |
| DELETE | `/alerts/api/{id}/` | 알람 삭제 |
| GET | `/alerts/api/my-status/` | 내 알람 현황 |
| GET | `/alerts/api/worker-summary/` | 작업자별 알람 요약 |
| POST | `/alerts/api/events/{id}/resolve/` | 이벤트 RESOLVED 처리 (알람 팝업 확인 시 호출) |

---

### 지오펜스 API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/geofences/` | 지오펜스 목록 |
| POST | `/api/geofences/` | 지오펜스 생성 |
| GET | `/api/geofences/{id}/` | 지오펜스 상세 |
| PUT/PATCH | `/api/geofences/{id}/` | 지오펜스 수정 |
| DELETE | `/api/geofences/{id}/` | 지오펜스 삭제 |
| GET | `/api/admin/geofences/` | 관리자용 지오펜스 목록 |
| GET/PUT | `/api/admin/geofences/{id}/` | 관리자용 지오펜스 상세 |

---

### 센서 데이터 수신 API (FastAPI → DRF 내부 통신)

| Method | Path | 호출 주체 | 설명 |
|--------|------|----------|------|
| POST | `/api/monitoring/gas/` | FastAPI gas_service | 가스 측정값 저장 |
| POST | `/api/monitoring/power/event/` | FastAPI power_service | 전력 ON/OFF 스냅샷 저장 |
| POST | `/api/monitoring/power/data/` | FastAPI power_service | 전력 측정값 (전류·전압·전력) 저장 |
| POST | `/api/positioning/receive/` | FastAPI ws_router / position_service | 작업자 위치 수신 (지오펜스 근접 시만 DB 저장) |

---

## fastapi-server (포트 8001)

### HTTP — 센서 데이터 수신

| Method | Path | 호출 주체 | 설명 |
|--------|------|----------|------|
| POST | `/api/sensors/info` | 가스 센서 장비 | 기기 정보 등록 (부팅 시 1회) |
| POST | `/api/sensors/gas` | 가스 센서 장비 | 가스 측정값 수신 → DRF 저장 + 공유 상태 갱신 |
| POST | `/api/power/onoff` | 전력 센서 장비 | ON/OFF 상태 수신 → DRF 저장(BackgroundTask) + 상태 갱신 |
| POST | `/api/power/current` | 전력 센서 장비 | 전류 수신 |
| POST | `/api/power/voltage` | 전력 센서 장비 | 전압 수신 |
| POST | `/api/power/watt` | 전력 센서 장비 | 전력(W) 수신 |
| GET | `/health/` | 헬스 체크 | `{"status": "ok"}` 반환 |

---

### WebSocket

| Path | 접속 주체 | 설명 |
|------|----------|------|
| `ws://localhost:8001/ws/sensors/` | 브라우저 | 1초마다 통합 페이로드 송출 (가스+전력+알람+작업자 위치) |
| `ws://localhost:8001/ws/position/` | IoT 위치 장비 | 위치 수신 → DRF 저장 + 공유 상태 갱신 |
| `ws://localhost:8001/ws/positions/` | 브라우저 | 1초마다 더미 작업자 위치 배열 송출 |

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

[IoT 위치 장비]
  WS :8001/ws/position/
    └→ DRF POST :8000/api/positioning/receive/

[더미 위치 브로드캐스트]
  WS :8001/ws/positions/
    └→ DRF POST :8000/api/positioning/receive/

[브라우저]
  WS :8001/ws/sensors/
    ← 공유 상태(websocket/state.py) 기반 페이로드
       · latest_gas_snapshot   (gas_service가 갱신)
       · active_alarms         (gas_service가 push, 송출 후 비움)
       · power_latest          (power_service가 갱신)
       · worker_positions      (ws/position/ 수신 시 갱신)
```

---

## 공유 상태 (fastapi-server/websocket/state.py)

HTTP Push 없이 같은 프로세스 내 모듈 간 직접 공유합니다.

| 변수 | 갱신 주체 | 소비 주체 |
|------|----------|----------|
| `latest_gas_snapshot` | gas_service | broadcast.py (/ws/sensors/) |
| `active_alarms` | gas_service | broadcast.py (송출 후 clear) |
| `power_latest` | power_service | broadcast.py → build_equipment() |
| `worker_positions` | ws_router (/ws/position/) | broadcast.py (/ws/sensors/) |

---

> ⚠️ **Phase 4 수정 예정 항목** (templates/css/js)
>
> 아래는 DRF 서버의 미사용 프론트엔드 파일로, Phase 4에서 삭제 또는 통합 예정입니다.
> - `templates/main_dashboard_CJY.html` / `main_dashboard_jhh.html`
> - `static/js/refactors/websocket_CJY.js` / `websocket_jhh.js` / `charts_CJY.js` / `gas-panel_jhh.js`
> - `static/css/dashboard_CJY.css`
> - `static/js/detail/` 폴더 전체 (구 구조, 활성 여부 검토 필요)
> - `dashboard/jhh/` 엔드포인트 (구 대시보드 뷰)
