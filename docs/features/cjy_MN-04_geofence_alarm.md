# 기능정의서 — MN-04 지오펜스-알람 연동 및 작업자 개인 알림 WebSocket

> 작성일: 2026-04-30
> 브랜치: feature/MN-04_refactor
> 커밋: b0f3df182996f1382f244046a46d50239d13063e (서버 로직) + 현재 채팅 세션 (WS 타겟팅)

---

## 1. 기능 목록표

| 대분류 | 화면명 | 기능ID | 기능명 | 기능 목적 | 사용자 시나리오 | 엣지 정보 | 유효성 처리 | 예외 조건 | 에러 처리 | 백엔드 처리 | 프론트엔드 처리 | 참고사항 |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| 알람 | 대시보드/모든 페이지 | MN-04-1 | 지오펜스 진입 감지 | 작업자가 위험구역에 들어오면 즉시 탐지 | IoT 위치 수신 → 지오펜스 30px 이내 진입 → 센서 위험 상태 확인 | 지오펜스 내부 진입 + 경계 30px 이내 모두 해당 | 필수 필드(worker_id, facility_id, x, y) 누락 시 에러 반환 | 위험 센서 없으면 알람 미발송 | Celery retry 3회 | DRF position_service → Celery fire_geofence_alarm_task | — | 기준: 지오펜스 polygon 경계 30px |
| 알람 | 대시보드/모든 페이지 | MN-04-2 | 지오펜스 알람 생성 | DB에 AlarmRecord/Event 기록 후 WS 브로드캐스트 | 알람 생성 → FastAPI /internal/alarms/push/ 호출 → active_alarms 큐 등록 | 동일 이벤트 12시간 병합 (중복 알람 방지) | alarm_type, risk_level, source_label, summary 필수 | event is None이면 WS 미전송 (중복 이벤트) | 태스크 실패 시 최대 3회 재시도 | DRF Celery → FastAPI 내부 HTTP → active_alarms 큐 | 관리자: AlarmPopup.show() | is_new_event=False면 팝업 미표시 |
| 알람 | 작업자 로그인 페이지 | MN-04-3 | 작업자 개인 WebSocket | 진입한 작업자 본인에게만 알람 직접 전송 | 작업자 브라우저 /ws/worker/{userId}/ 연결 → 지오펜스 알람 발생 시 즉시 팝업 | 작업자 WS 미연결 시 개인 전송 생략 (broadcast는 정상) | user_id로 연결 식별, 재연결 3초 대기 | worker_id WS 전송 실패 시 worker_clients에서 제거 | 전송 실패 시 자동 정리 후 계속 | FastAPI alarm_router → worker_clients[worker_id].send_json | worker-ws.js: type=worker_alert 수신 시 AlarmPopup.show() | alarm-ws.js(관리자)와 독립 동작 |
| 어드민 | 어드민 사이드바 | MN-04-4 | 사이드바 메뉴 링크 정비 | 설비/구역/지도 관리 페이지 연결 활성화 | 어드민 사이드바에서 설비관리·구역관리·지도관리 클릭 | — | — | — | — | — | admin_sidebar.html 링크 수정 | 설비: /admin-panel/facility/, 지도 관리 신규 추가 |

---

## 2. 요구사항 정의서

### MN-04-1 지오펜스 진입 감지

**중요도:** 높음

**기능 목적:**
IoT 장비가 위치 데이터를 보낼 때마다, 해당 작업자의 좌표가 위험구역(GeoFence)에 진입했는지 실시간으로 판단한다.

**요구사항 상세:**
- 진입 판정 기준 1: `GeoFence.contains_point(x, y)` — 지오펜스 polygon 내부
- 진입 판정 기준 2: 지오펜스 polygon 경계로부터 30픽셀 이내 (`_distance_to_geofence()`)
- 두 조건 중 하나라도 해당하면 DB 저장 + 알람 체크 진행
- 지오펜스 외부이면 DB 저장 없이 종료 (WebSocket 표시 전용)

**백엔드 처리:**
`position_service.handle_position_receive()` → `_is_near_any_geofence()` → 진입 시 `WorkerPosition` 생성 → `update_geofence_cache()` → `_get_dangerous_sensors_in_geofence()` → Celery 태스크 발행

**예외 사항:**
- GeoFence가 존재하지 않는 시설: 저장 없이 통과
- 센서/장비가 없거나 모두 normal 상태: 알람 미발생

---

### MN-04-2 지오펜스 알람 생성

**중요도:** 높음

**기능 목적:**
위험구역 진입 감지 후 AlarmRecord + Event를 DB에 기록하고 FastAPI WebSocket 큐에 알람을 추가한다.

**요구사항 상세:**
- `create_alarm_and_event()` 호출: 12시간 이내 동일 이벤트는 AlarmRecord만 추가 (Event 중복 생성 방지)
- `is_new_event`: 새 Event 생성 여부 → 프론트엔드 팝업 표시 조건
- WS 페이로드에 `worker_id` 포함 → alarm_router에서 개인 전송에 활용
- BROADCAST_INTERVAL을 30초 → 2초로 변경하여 알람 응답성 향상

**백엔드 처리:**
Celery `fire_geofence_alarm_task` → `create_alarm_and_event()` → `_push_to_ws()` → FastAPI `/internal/alarms/push/`

**예외 사항:**
- FastAPI 서버 미기동: WS 알림 누락, DB 기록은 보존
- event=None (중복 이벤트): WS 미전송, DB AlarmRecord는 기록

---

### MN-04-3 작업자 개인 WebSocket

**중요도:** 중간

**기능 목적:**
지오펜스 진입 알람 발생 시 해당 작업자의 브라우저에만 직접 팝업을 전송한다. 관리자 브로드캐스트와 독립적으로 동작한다.

**요구사항 상세:**
- FastAPI `/ws/worker/{user_id}/` 엔드포인트 신규 추가
- `worker_clients: dict[int, WebSocket]`에 연결 등록/해제 관리
- `alarm_router.push_alarm()`: `alarm_type == "geofence_intrusion"` 이고 `worker_id` 있을 때 개인 전송
- 프론트엔드 `worker-ws.js`: `Auth.getMe()`로 user.id 획득 후 연결, `type: "worker_alert"` 수신 시 `AlarmPopup.show()` 호출

**백엔드 처리:**
alarm_router → `worker_clients.get(alarm.worker_id)` → `ws.send_json({"type": "worker_alert", ...payload})`

**예외 사항:**
- 작업자 WS 미연결: 개인 전송 생략, 관리자 broadcast는 정상 동작
- WS 전송 실패: `worker_clients`에서 해당 항목 제거 후 계속

---

## 3. API 명세서

### FastAPI 내부 엔드포인트

**POST /internal/alarms/push/** (DRF Celery → FastAPI)

```json
// Request
{
  "alarm_type": "geofence_intrusion",
  "risk_level": "danger",
  "source_label": "위험구역A",
  "summary": "[긴급] 작업자가 위험구역 '위험구역A'에 진입했습니다. (CO센서 임계치 초과)",
  "is_new_event": true,
  "event_id": 42,
  "worker_id": 7
}

// Response
{ "ok": true }
```

**가스 알람 페이로드 (alarm_type: gas_threshold)**
```json
{
  "alarm_type": "gas_threshold",
  "risk_level": "danger",
  "source_label": "CO센서-1",
  "summary": "[긴급] CO (일산화탄소) 위험 수준 초과 (55.0 ppm) — ...",
  "is_new_event": true,
  "event_id": 41,
  "gas_type": "co",
  "measured_value": 55.0,
  "threshold_value": 50.0
}
```

### FastAPI WebSocket 엔드포인트

| 엔드포인트 | 방향 | 역할 |
|:--|:--|:--|
| `WS /ws/sensors/` | 서버 → 브라우저 | 관리자용 통합 브로드캐스트 (가스+전력+작업자+알람) |
| `WS /ws/worker/{user_id}/` | 서버 → 작업자 브라우저 | 작업자 개인 지오펜스 진입 알람 |
| `WS /ws/position/` | IoT → 서버 | IoT 위치 데이터 수신 |

**worker_alert 페이로드 (작업자 수신)**
```json
{
  "type": "worker_alert",
  "alarm_type": "geofence_intrusion",
  "risk_level": "danger",
  "source_label": "위험구역A",
  "summary": "[긴급] 작업자가 위험구역 '위험구역A'에 진입했습니다.",
  "is_new_event": true,
  "event_id": 42,
  "worker_id": 7
}
```

### DRF 위치 수신

**POST /api/positioning/receive/**

```json
// Request (FastAPI → DRF)
{
  "worker_id": 7,
  "facility_id": 1,
  "x": 120.5,
  "y": 80.3,
  "measured_at": "2026-04-30T04:00:00+00:00"
}

// Response 201
{ "id": 123, "worker_id": 7, ... }
```

---

## 4. 흐름도

```
[IoT 장비]
    │  WS /ws/position/ (worker_id, facility_id, x, y)
    ▼
[FastAPI ws_router.position_stream()]
    │  HTTP POST /api/positioning/receive/
    ▼
[DRF positioning/views.py → handle_position_receive()]
    │
    ├─ 지오펜스 30px 이내? NO → return None (저장 안 함)
    │
    └─ YES → WorkerPosition.create() → update_geofence_cache()
                │
                ├─ current_geofence 없음 → 종료
                │
                └─ current_geofence 있음
                        │
                        └─ _get_dangerous_sensors_in_geofence()
                                │
                                ├─ 위험 센서 없음 → 종료
                                │
                                └─ 위험 센서 있음
                                        │
                                        ▼
                               [Celery fire_geofence_alarm_task.delay()]
                                        │
                                        └─ create_alarm_and_event()
                                                │
                                                └─ _push_to_ws()
                                                        │
                                                        ▼
                                          [FastAPI POST /internal/alarms/push/]
                                                        │
                                          ┌─────────────┴──────────────┐
                                          │                            │
                                 active_alarms.append()     worker_clients.get(worker_id)
                                          │                            │
                                 [alarm_flush_loop()]          WS.send_json(worker_alert)
                                          │                            │
                                   broadcast to                [작업자 브라우저]
                                  sensor_clients                AlarmPopup.show()
                                          │
                                   [관리자 브라우저]
                                   AlarmPopup.show()
```

---

## 5. 파일별 역할

| 서버 | 파일 | 변경 | 역할 |
|:--|:--|:--|:--|
| DRF | `apps/positioning/services/position_service.py` | **수정** | 지오펜스 진입 감지 + 위험 센서 체크 + Celery 태스크 발행 |
| DRF | `apps/alerts/tasks.py` | **수정** | `fire_geofence_alarm_task` Celery 태스크 추가 |
| DRF | `templates/components/admin_sidebar.html` | **수정** | 어드민 사이드바 설비/구역/지도 링크 활성화 |
| FastAPI | `websocket/state.py` | **수정** | `worker_clients: dict[int, WebSocket]` 추가 |
| FastAPI | `websocket/routers/ws_router.py` | **수정** | `/ws/worker/{user_id}/` 엔드포인트 추가, BROADCAST_INTERVAL 30→2 |
| FastAPI | `internal/routers/alarm_router.py` | **수정** | AlarmPayload에 `worker_id`, `gas_type` optional 추가, 지오펜스 알람 시 작업자 개인 전송 로직 |
| Frontend | `static/js/shared/worker-ws.js` | **신규** | 작업자 개인 WS 연결, `worker_alert` 수신 시 AlarmPopup 호출 |
| Frontend | `templates/dashboard/main.html` | **수정** | worker-ws.js script 태그 추가 |
| Frontend | `templates/snb_details/monitoring_realtime.html` | **수정** | worker-ws.js script 태그 추가 |
| Frontend | `templates/snb_details/monitoring_events.html` | **수정** | worker-ws.js script 태그 추가 |
| Frontend | `templates/snb_details/event_detail.html` | **수정** | worker-ws.js script 태그 추가 |

---

## 6. 디렉토리 경로

```
diconai/
├── drf-server/
│   ├── apps/
│   │   ├── alerts/
│   │   │   └── tasks.py                     ← fire_geofence_alarm_task 추가
│   │   └── positioning/
│   │       └── services/
│   │           └── position_service.py      ← 위험 센서 체크 + Celery 발행
│   ├── static/
│   │   └── js/
│   │       └── shared/
│   │           └── worker-ws.js             ← 신규: 작업자 개인 WS
│   └── templates/
│       ├── components/
│       │   └── admin_sidebar.html           ← 링크 수정
│       ├── dashboard/
│       │   └── main.html                    ← worker-ws.js 추가
│       └── snb_details/
│           ├── monitoring_realtime.html     ← worker-ws.js 추가
│           ├── monitoring_events.html       ← worker-ws.js 추가
│           └── event_detail.html           ← worker-ws.js 추가
└── fastapi-server/
    ├── internal/
    │   └── routers/
    │       └── alarm_router.py              ← worker_id 처리, gas_type optional
    └── websocket/
        ├── state.py                         ← worker_clients 추가
        └── routers/
            └── ws_router.py                 ← /ws/worker/{user_id}/ 추가
```

---

## 7. URL 정의서

| 서버 구분 | 메서드 | URL | 설명 |
|:--|:--|:--|:--|
| FastAPI (내부) | POST | `/internal/alarms/push/` | DRF Celery → FastAPI WS 큐 등록 (localhost 전용) |
| FastAPI (WS) | WebSocket | `/ws/sensors/` | 관리자 브라우저 통합 데이터 스트림 |
| FastAPI (WS) | WebSocket | `/ws/worker/{user_id}/` | 작업자 개인 알림 스트림 (신규) |
| FastAPI (WS) | WebSocket | `/ws/position/` | IoT 위치 데이터 수신 |
| DRF | POST | `/api/positioning/receive/` | FastAPI → DRF 위치 저장 |
| 어드민 | GET | `/admin-panel/facility/` | 설비 관리 (사이드바 링크 수정) |
| 어드민 | GET | `/admin-panel/geofence/` | 구역 관리 |
| 어드민 | GET | `/admin-panel/map-editor/` | 지도 관리 (사이드바 신규 추가) |

---

## 8. 생성/처리 조건

### 지오펜스 진입 판정
- `GeoFence.contains_point(x, y)` = True (Ray Casting) **OR**
- `_distance_to_geofence(x, y, polygon)` ≤ 30px
- → 두 조건 중 하나라도 참이면 진입으로 판정

### 위험 센서 판정 우선순위
- `_RISK_ORDER = {"warning": 1, "danger": 2}`
- 지오펜스 polygon 안에 위치한 GasSensor + PowerDevice 중 max_risk_level이 가장 높은 것 반환
- 모두 "normal"이면 None 반환 → 알람 미발송

### 이벤트 병합 조건 (중복 알람 방지)
- 동일 `facility_id` + `alarm_type` + `geofence_id` 조합으로 12시간 이내 Event가 있으면 AlarmRecord만 추가
- `is_new_event=False` → WS 전송은 하되 팝업 미표시

### 작업자 개인 전송 조건
- `alarm_type == "geofence_intrusion"` AND `worker_id is not None`
- `worker_clients.get(worker_id)` 존재 시 즉시 `send_json`
- 전송 실패(연결 끊김) → `worker_clients`에서 해당 항목 제거

### WS 브로드캐스트 주기
- 전체 브로드캐스트: 2초 간격 (기존 30초 → 2초로 단축)
- 신규 이벤트 알람 전용 flush: 2초 간격 (`is_new_event=True` 체크)

---

## 9. 서버 실행 명령어

```bash
# 1. DRF 서버 (포트 8000)
cd drf-server
python manage.py runserver 0.0.0.0:8000

# 2. Celery 워커 (알람 태스크 처리)
cd drf-server
celery -A config.celery worker --loglevel=info

# 3. FastAPI 서버 (포트 8001)
cd fastapi-server
uvicorn main:app --reload --port 8001

# 4. Redis (Celery 브로커, 별도 터미널 또는 서비스)
redis-server
# 또는
sudo service redis start

# 테스트용 더미 위치 데이터 전송 (WebSocket 클라이언트)
# Python 예시
python - <<'EOF'
import asyncio, websockets, json

async def send_position():
    async with websockets.connect("ws://127.0.0.1:8001/ws/position/") as ws:
        await ws.send(json.dumps({
            "worker_id": 1,
            "facility_id": 1,
            "x": 120.0,   # 지오펜스 내부 좌표로 변경
            "y": 80.0
        }))
        print(await ws.recv())

asyncio.run(send_position())
EOF
```

---

## 10. 테스트 방법 및 결과

### 사전 조건 확인
```bash
# 활성 지오펜스 확인
cd drf-server && python manage.py shell -c "
from apps.geofence.models import GeoFence
for g in GeoFence.objects.filter(is_active=True):
    print(g.id, g.name, g.facility_id, g.polygon[:2])
"

# 위험 상태 센서 확인
python manage.py shell -c "
from apps.monitoring.models import GasData
latest = GasData.objects.exclude(max_risk_level='normal').order_by('-measured_at')[:5]
for d in latest:
    print(d.gas_sensor.device_name, d.max_risk_level, d.measured_at)
"
```

### 테스트 포인트 1 — 지오펜스 진입 감지

**확인 방법:** 지오펜스 내부 좌표로 위치 데이터 전송

```bash
# DRF Celery 워커 로그에서 확인
INFO celery.task - 지오펜스 알람 푸시 | geofence=위험구역A worker=1 risk=danger new_event=True

# FastAPI 로그에서 확인
[position] DRF 201: worker=1 (120.0, 80.0)
```

**기대 결과:**
- `WorkerPosition` DB 레코드 생성됨
- `AlarmRecord` + `Event` DB 생성됨
- FastAPI `active_alarms` 큐에 데이터 추가됨

### 테스트 포인트 2 — 관리자 브라우저 팝업

**확인 방법:** 관리자 계정으로 대시보드 접속 → 개발자 도구 Console

```javascript
// 브라우저 Console에서 확인
// WS 연결 확인
// FastAPI 로그: [ws/sensors] 브라우저 연결됨 (총 1개)

// 2초 내 알람 수신 확인 (Network 탭 WS 메시지)
// { "alarms": [{ "alarm_type": "geofence_intrusion", "risk_level": "danger", ... }], ... }
```

**기대 결과:** 관리자 화면에 위험 팝업 모달 표시

### 테스트 포인트 3 — 작업자 개인 WS 알람

**확인 방법:**

```bash
# 작업자 계정으로 대시보드 접속 후 개발자 도구 Network > WS 탭에서
# ws://127.0.0.1:8001/ws/worker/{userId}/ 연결 확인

# FastAPI 로그 확인
[ws/worker] 작업자 연결됨 user_id=1
```

```javascript
// 브라우저 Console에서 수동 테스트
const ws = new WebSocket('ws://127.0.0.1:8001/ws/worker/1/');
ws.onmessage = e => console.log(JSON.parse(e.data));
// 지오펜스 진입 시 수신:
// { "type": "worker_alert", "alarm_type": "geofence_intrusion", "risk_level": "danger", ... }
```

**기대 결과:** 작업자 화면에 `[긴급] 작업자가 위험구역 '...'에 진입했습니다.` 팝업 표시

### 테스트 포인트 4 — 지오펜스 외부 좌표 (저장 안 됨 확인)

```bash
# 지오펜스와 거리가 먼 좌표 (예: x=9999, y=9999) 전송 시
# DRF 로그: 저장 로직 진입 안 함 (None 반환)
# WorkerPosition DB에 레코드 없음
python manage.py shell -c "
from apps.positioning.models import WorkerPosition
print(WorkerPosition.objects.filter(worker_id=1).count())
"
```

### 테스트 포인트 5 — 중복 이벤트 병합 확인

```bash
# 동일 작업자로 동일 지오펜스 재진입 (12시간 이내)
# 기대: AlarmRecord만 추가, Event 신규 생성 없음
# is_new_event=False → 관리자/작업자 팝업 미표시

# Celery 로그 확인
INFO - 지오펜스 알람 푸시 | geofence=위험구역A worker=1 risk=danger new_event=False
```
