# 기능정의서 — CM-07 / MN-03 가스 알람 이벤트 생성 및 실시간 알림

> 작성일 : 2026-04-23
> 브랜치 : feature/cm07-mn03-alarm-event.v1
> 작성자 : jhh
> 선행 문서 : 기능정의서.md (가스 센서 데이터 수신 및 저장)

---

## 1. 기능 목록표

| 대분류 | 화면명 | 기능ID | 기능명 | 기능 목적 | 사용자 시나리오 | 엣지 정보 | 유효성 처리 | 예외 조건 | 에러 처리 | 백엔드 처리 | 프론트엔드 처리 | 참고사항 |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| 알람 | - | CM-07 | 가스 임계치 알람 생성 | GasData 저장 후 임계치 초과 가스가 있으면 AlarmRecord + Event를 자동 생성한다 | GasData 저장 완료 시 서비스 레이어에서 자동 호출 | 동일 센서·동일 알람 유형 활성 Event 존재 시 병합(AlarmRecord만 추가) | 가스별 위험도 필드 기준(warning/danger) | 병합 윈도우(12시간) 초과 시 기존 Event 자동 종료 후 신규 생성 | 알람 생성 실패해도 GasData 저장은 성공으로 처리(독립 트랜잭션) | DRF: trigger_gas_alarms() → create_alarm_and_event() | 없음 (서버 내부) | 가스 9종 각각 독립적으로 AlarmRecord 생성 |
| 모니터링 | 대시보드 | MN-03 | 실시간 알람 팝업 | 새 Event 생성 시 브라우저에 WebSocket으로 즉시 팝업 표시 | 임계치 초과 → DRF 알람 생성 → FastAPI WS Push → 브라우저 팝업 | 기존 Event에 병합된 경우(신규 아님) 팝업 미발송 | DRF 응답의 alarms 배열 비어있으면 Push 생략 | FastAPI WS 앱(8002) 연결 불가 시 경고 로그만 남기고 무시 | WS Push 실패는 silent fail (가스 저장 자체는 영향 없음) | FastAPI sensors(8001) → POST /internal/alarm/(8002) → ws/sensors/ 페이로드에 포함 | AlarmPopup.show() 호출, 10초 자동 닫힘, 큐 순서대로 처리 | 동시에 여러 가스 초과 시 알람별로 순차 팝업 |
| 모니터링 | 이벤트 현황 패널 | MN-03 | 이벤트 현황 패널 표시 | 발생한 이벤트를 위험/주의 색상 구분 + 한글 설명으로 표시 | 페이지 로드 시 최근 10건 조회, 실시간 알람 수신 시 상단 추가 | API 응답 필드명(risk_level, alarm_type)과 프론트 기대 필드명(alarm_level, message) 불일치 보정 | AlarmRecordSerializer에서 alarm_level, message 필드 추가 제공 | message 없을 시 gas_type + measured_value로 자동 조합 | - | AlarmRecordSerializer: alarm_level(=risk_level), message(=조합) 필드 추가 | event-panel.js addItem() 호출 — 위험=빨간점, 주의=노란점 | event-panel.js는 공유 파일로 미수정 |

---

## 2. 요구사항 정의서

### [REQ-CM-07-v2] 가스 임계치 알람 생성

**분류** 기능적 요구사항
**중요도** 상

**기능 목적**
GasData 저장 완료 직후 각 가스별 위험도를 확인하여 warning 또는 danger 상태인 가스마다 AlarmRecord와 Event를 자동 생성한다.

**요구사항 상세 설명**

- GasData 저장 후 co, h2s, co2, o2, no2, so2, o3, nh3, voc 9종의 `{gas}_risk` 필드를 순서대로 확인한다.
- `warning` 또는 `danger`인 가스마다 `create_alarm_and_event()`를 호출한다.
- 동일 센서 + 동일 `alarm_type`으로 활성(active/acknowledged/in_progress) Event가 존재하면 AlarmRecord만 추가하고 Event는 새로 만들지 않는다. (병합)
- 병합 가능 시간 윈도우(12시간)를 초과한 경우 기존 Event를 자동 종료(resolved)하고 새 Event를 생성한다.
- AlarmRecord에 `gas_type`, `measured_value`, `threshold_value`, `risk_level`을 모두 기록한다.
- `threshold_value`는 위험도에 따라 다름:
  - 일반 가스(o2 제외): warning → `normal_max`, danger → `warning_max`
  - o2: warning → `normal_min`(18.0%), danger → `warning_min`(16.0%)
- 알람 생성은 `@transaction.atomic`으로 처리된다. GasData 저장 트랜잭션과 별개로 실행된다.

**백엔드 처리 및 인터페이스**

- `apps/monitoring/utils/gas_thresholds.py` — 임계치 상수, `get_threshold_value()`
- `apps/monitoring/services/gas_alarm.py` — `trigger_gas_alarms()`: GasData 객체를 받아 알람 생성 후 새 Event 목록 반환
- `apps/alerts/services/event_service.py` — `create_alarm_and_event()`: AlarmRecord + Event 생성/병합 핵심 로직
- `apps/monitoring/serializers/gas_data.py` — `GasDataCreateSerializer.create()` 내에서 `trigger_gas_alarms()` 호출, 결과를 `gas_data._alarms`에 임시 저장
- `apps/monitoring/views/gas_data.py` — `_alarms`를 응답의 `alarms` 필드로 반환

**예외 사항 및 비고**

- 알람 생성 실패(DB 오류 등)는 GasData 저장 결과와 독립적으로 처리됨
- 병합 시(`alarm is None` 반환) 프론트 알림 미발송 (중복 팝업 방지)
- lel은 임계치 미정의로 알람 대상에서 제외

---

### [REQ-MN-03-v2] 실시간 알람 WebSocket 전달

**분류** 기능적 요구사항
**중요도** 상

**기능 목적**
새 Event가 생성된 경우에만 FastAPI WebSocket 앱으로 알람 데이터를 Push하여 브라우저에 실시간 팝업을 표시한다.

**요구사항 상세 설명**

- DRF `POST /api/monitoring/gas/` 응답의 `alarms` 배열이 비어있지 않을 때만 `POST /internal/alarm/`을 호출한다.
- FastAPI sensors(8001)는 DRF 응답 수신 후 WebSocket 앱(8002)으로 가스 스냅샷(`/internal/gas-snapshot/`)과 알람(`/internal/alarm/`)을 각각 Push한다.
- WebSocket 앱은 `active_alarms` 인메모리 큐에 알람을 저장하고, `/ws/sensors/` 틱 시 페이로드에 포함 후 큐를 비운다.
- 브라우저는 `data.alarms` 배열을 수신하면 각 알람마다 `AlarmPopup.show()`를 호출한다.
- 동시에 여러 가스가 초과된 경우 큐 순서대로 순차 팝업된다. (10초 자동 닫힘)
- WebSocket 앱에 가스 스냅샷(`co`, `co_risk` 등 9종)도 함께 Push되어 대시보드 가스 테이블이 실시간 갱신된다.

**백엔드 처리 및 인터페이스**

- `fastapi-server/routers/sensors.py` — DRF 응답 처리 후 8002로 gas-snapshot + alarm Push
- `fastapi-server/core/config.py` — `FASTAPI_WS_BASE_URL` 환경변수 추가
- `fastapi-server/websocket_jhh.py` ← jhh 작업본 (원본 websocket.py 미수정)
  - `active_alarms: list[dict]` — 알람 큐 (인메모리)
  - `latest_gas_snapshot: dict` — 최신 가스 측정값 캐시
  - `POST /internal/alarm/` — 알람 Push 수신
  - `POST /internal/gas-snapshot/` — 가스 스냅샷 수신
  - `get_temp_sensor_data()` — WS 페이로드에 `alarms`, `co_risk` 등 포함
- `drf-server/static/js/refactors/websocket_jhh.js` ← jhh 작업본 (원본 websocket.js 미수정)
  - WS 연결 포트: 8002 (`ws://127.0.0.1:8002/ws/sensors/`, `/ws/positions/`)
  - `data.alarms` 처리 → `AlarmPopup.show()` + `EventPanel.addItem()`
  - `worker_positions` 객체 → 배열 변환 후 `MapPanel.updateWorkerPositions()` 전달
  - 가스 테이블 9종 실시간 갱신 (`data.co_risk` 등 위험도 반영)
- `drf-server/templates/main_dashboard_jhh.html` — `websocket_jhh.js` 로드 (websocket.js 아님)

**예외 사항 및 비고**

- WS Push 실패(8002 미실행 등)는 `logger.warning`만 남기고 센서 수신 응답에는 영향 없음
- `active_alarms.clear()`는 WS 틱마다 초기화되므로 팝업은 1회만 발송됨
- 원본 `websocket.js`는 `data.level === '위험'` 더미 기반 / `websocket_jhh.js`는 `data.alarms` DRF 실제 알람 기반

---

### [REQ-MN-03-v3] 이벤트 현황 패널 색상 및 설명 표시

**분류** 기능적 요구사항
**중요도** 중

**기능 목적**
이벤트 현황 패널에서 위험(danger)은 빨간 점, 주의(warning)는 노란 점으로 구분하고, "gas_threshold" 대신 한글 설명("CO 임계치 초과 (250.0 ppm)")을 표시한다.

**요구사항 상세 설명**

- `event-panel.js`(공유 파일)는 `alarm_level` 필드로 위험도를 판단하고 `message` 필드로 설명을 표시한다.
- `AlarmRecordSerializer`가 내려주는 필드명은 `risk_level`, `alarm_type`으로 불일치 → 전부 노란 점, "gas_threshold" 표시 문제 발생.
- `AlarmRecordSerializer`에 `alarm_level`(`risk_level` alias)과 `message`(gas_type + measured_value 조합) 필드를 추가하여 해결.
- `message` 생성 규칙: `{GAS_TYPE} 임계치 초과 ({measured_value} ppm)` — gas_type 없으면 alarm_type 그대로 표시.

**백엔드 처리 및 인터페이스**

- `apps/alerts/serializers/alarm_record.py`
  - `alarm_level = serializers.CharField(source="risk_level")` 추가
  - `message = serializers.SerializerMethodField()` 추가
  - `get_message()`: gas_type + measured_value → 한글 설명 조합

**예외 사항 및 비고**

- `event-panel.js`는 팀 공유 파일이므로 수정 없음
- 실시간 WebSocket 경로(websocket_jhh.js)는 이미 `alarm_level`, `message` 필드를 올바르게 사용 중이므로 별도 수정 불필요

---

## 3. API 명세서

### CM-07 — DRF 가스 저장 + 알람 응답

#### `POST /api/monitoring/gas/`

**기능** 가스 데이터 저장 + 임계치 초과 시 알람 생성
**사용자** FastAPI sensors(8001) 내부 호출
**메서드** POST
**URL** /api/monitoring/gas/

**Request**
Content-Type: application/json

```json
{
  "device_id": "63200c3afd12",
  "measured_at": "2026-04-23T10:00:00+00:00",
  "co": 250, "h2s": 4, "co2": 560,
  "o2": 20.15, "no2": 1.2, "so2": 0.8,
  "o3": 0.02, "nh3": 8, "voc": 0.3,
  "co_risk": "danger", "h2s_risk": "normal", "co2_risk": "normal",
  "o2_risk": "normal", "no2_risk": "normal", "so2_risk": "normal",
  "o3_risk": "normal", "nh3_risk": "normal", "voc_risk": "normal",
  "raw_payload": { "timestamp": "...", "lel": 2, "...": "..." }
}
```

**Response**

Success (알람 없음): 201 Created
```json
{ "id": 10, "received": true, "alarms": [] }
```

Success (알람 생성됨): 201 Created
```json
{
  "id": 11,
  "received": true,
  "alarms": [
    {
      "event_id": 5,
      "alarm_type": "gas_threshold",
      "gas_type": "co",
      "risk_level": "danger",
      "measured_value": 250.0,
      "threshold_value": 200.0,
      "source_label": "가스센서 A",
      "summary": "CO 임계치 초과 (250.0 ppm)",
      "is_new_event": true
    }
  ]
}
```

Error: 400 Bad Request
```json
{ "device_id": "등록되지 않은 장치입니다: 63200c3afd12" }
```

---

### MN-03 — FastAPI 내부 Push 엔드포인트 (websocket_jhh.py, 8002)

#### `POST /internal/alarm/`

**기능** 알람 이벤트 수신 후 WS 큐에 저장
**사용자** FastAPI sensors(8001) 내부 호출
**메서드** POST
**URL** /internal/alarm/

**Request**
```json
{
  "alarms": [
    {
      "event_id": 5,
      "gas_type": "co",
      "risk_level": "danger",
      "summary": "CO 임계치 초과 (250.0 ppm)",
      "source_label": "가스센서 A"
    }
  ]
}
```

**Response**
```json
{ "queued": 1 }
```

---

#### `POST /internal/gas-snapshot/`

**기능** 최신 가스 측정값 + 위험도 캐시 갱신
**사용자** FastAPI sensors(8001) 내부 호출
**메서드** POST
**URL** /internal/gas-snapshot/

**Request**
```json
{
  "snapshot": {
    "co": 250, "h2s": 4, "co2": 560,
    "o2": 20.15, "no2": 1.2, "so2": 0.8,
    "o3": 0.02, "nh3": 8, "voc": 0.3,
    "co_risk": "danger", "h2s_risk": "normal",
    "co2_risk": "normal", "o2_risk": "normal",
    "no2_risk": "normal", "so2_risk": "normal",
    "o3_risk": "normal", "nh3_risk": "normal", "voc_risk": "normal"
  }
}
```

**Response**
```json
{ "ok": true }
```

---

### MN-03 — AlarmRecord 목록 조회 (이벤트 현황 패널)

#### `GET /alerts/api/`

**기능** 최근 AlarmRecord 목록 조회 (이벤트 현황 패널 초기 로드)
**사용자** 브라우저 (event-panel.js)
**메서드** GET
**URL** /alerts/api/?ordering=-created_at&limit=10

**Response**
```json
[
  {
    "id": 1,
    "alarm_type": "gas_threshold",
    "risk_level": "danger",
    "alarm_level": "danger",
    "gas_type": "co",
    "measured_value": 250.0,
    "threshold_value": 200.0,
    "message": "CO 임계치 초과 (250.0 ppm)",
    "sensor_name": "가스센서 A",
    "created_at": "2026-04-23T11:42:38Z"
  }
]
```

---

## 4. 흐름도

```
[dummy_sender.py / 에어위드 센서]
        │  POST /api/sensors/gas  (1초 주기)
        ▼
[FastAPI sensors — 8001 / main.py]
  1. GasDataPayload 검증 + 위험도 계산
  2. POST /api/monitoring/gas/ (DRF, httpx timeout 5s)
        │
        ▼
[DRF — apps/monitoring]
  3. GasDataCreateSerializer.create()
     ├─ GasData DB 저장
     ├─ GasSensor.last_reading 갱신
     └─ trigger_gas_alarms(gas_data)
          └─ 각 가스 {gas}_risk 순회
               ├─ normal → 건너뜀
               └─ warning/danger → create_alarm_and_event()
                    ├─ 활성 Event 존재 + 12h 이내 → AlarmRecord만 추가 (병합)
                    │   return (event, None)  ← 알림 미발송
                    └─ 없음 or 12h 초과 → Event + AlarmRecord + EventLog 생성
                        return (event, alarm) ← 알림 발송
  4. 응답: {"id":..., "alarms": [...새 Event만 포함...]}
        │
        ▼
[FastAPI sensors — 8001 / routers/sensors.py]
  5. POST /internal/gas-snapshot/  → 8002 (항상)
  6. POST /internal/alarm/         → 8002 (alarms 있을 때만)
        │
        ▼
[FastAPI websocket — 8002 / websocket_jhh.py]
  7. active_alarms 큐에 저장
  8. /ws/sensors/ 다음 틱(1초)에 페이로드에 포함
     { ...전력/AI 더미..., alarms: [...], co: 250, co_risk: "danger", ... }
  9. active_alarms.clear()
        │
        ▼
[브라우저 — websocket_jhh.js]
 10. data.alarms 수신 → AlarmPopup.show() (10초 자동 닫힘, 큐 순서대로)
                      → EventPanel.addItem() (이벤트 현황 패널 실시간 추가)
 11. data.co_risk 등 → 가스 테이블 9종 실시간 갱신
 12. data.worker_positions(객체) → 배열 변환 → MapPanel.updateWorkerPositions()

[브라우저 페이지 로드 — event-panel.js]
 13. GET /alerts/api/?ordering=-created_at&limit=10
 14. AlarmRecordSerializer → alarm_level(=risk_level), message(=한글 조합) 포함
 15. addItem() → 위험=빨간 점, 주의=노란 점, 한글 설명 표시
```

---

## 5. 디렉토리 경로

```
fastapi-server/
├── core/
│   ├── config.py               # DRF_BASE_URL, FASTAPI_WS_BASE_URL 환경변수
│   └── gas_thresholds.py       # 임계치 상수 + 위험도 판정 함수
├── routers/
│   └── sensors.py              # DRF 호출 + WS Push (gas-snapshot, alarm)
├── websocket.py                # 원본 — 조원 공유 파일, 미수정
└── websocket_jhh.py            # jhh 작업본 — /internal/alarm/, /internal/gas-snapshot/,
                                #  active_alarms 큐, latest_gas_snapshot 캐시 추가

drf-server/
├── apps/monitoring/
│   ├── utils/
│   │   └── gas_thresholds.py   # DRF용 임계치 상수 + get_threshold_value()
│   ├── services/
│   │   └── gas_alarm.py        # trigger_gas_alarms(): GasData → AlarmRecord/Event
│   ├── serializers/
│   │   └── gas_data.py         # create() 내 trigger_gas_alarms() 호출
│   └── views/
│       └── gas_data.py         # 응답에 alarms 배열 포함
├── apps/alerts/
│   ├── models/
│   │   ├── alarm_record.py     # AlarmRecord (불변, event FK만 수정 가능)
│   │   ├── event.py            # Event (병합/상태전환 대상)
│   │   └── event_log.py        # EventLog (APPEND-ONLY 감사 로그)
│   ├── serializers/
│   │   └── alarm_record.py     # alarm_level(alias), message(한글 조합) 필드 추가
│   └── services/
│       └── event_service.py    # create_alarm_and_event() + acknowledge_event()
└── static/js/refactors/
    ├── websocket.js            # 원본 — 조원 공유 파일, 미수정
    ├── websocket_jhh.js        # jhh 작업본 — data.alarms 팝업, 9종 가스 테이블,
    │                           #  포트 8002, worker_positions 객체→배열 변환
    └── event-panel.js          # 원본 — 조원 공유 파일, 미수정
templates/
└── main_dashboard_jhh.html     # websocket_jhh.js 로드 (websocket.js 아님)
```

---

## 6. URL 정의서

| 구분 | 서버 | 메서드 | URL | 설명 |
|------|------|--------|-----|------|
| 센서 수신 | FastAPI 8001 (main.py) | POST | /api/sensors/gas | 가스 측정값 수신 (1초 주기) |
| 가스 저장 | DRF 8000 | POST | /api/monitoring/gas/ | GasData 저장 + 알람 생성 |
| 알람 Push | FastAPI 8002 (websocket_jhh.py) | POST | /internal/alarm/ | 새 Event 알람 큐 저장 |
| 스냅샷 Push | FastAPI 8002 (websocket_jhh.py) | POST | /internal/gas-snapshot/ | 최신 가스 측정값 캐시 갱신 |
| 대시보드 스트리밍 | FastAPI 8002 (websocket_jhh.py) | WS | /ws/sensors/ | 1초 주기 통합 페이로드 브라우저 전송 |
| 위치 수신 | FastAPI 8002 (websocket_jhh.py) | WS | /ws/positions/ | IoT 디바이스 위치 수신 → DRF 저장 |
| 이벤트 목록 | DRF 8000 | GET | /alerts/api/ | AlarmRecord 목록 (이벤트 현황 패널) |
| jhh 대시보드 | DRF 8000 | GET | /dashboard/jhh/ | jhh 작업본 대시보드 페이지 |

---

## 7. 알람 생성 조건 (가스별 임계치)

| 가스 | 단위 | warning 기준 | danger 기준 |
|------|------|-------------|------------|
| CO   | ppm  | ≥ 25        | ≥ 200      |
| H2S  | ppm  | ≥ 10        | ≥ 15       |
| CO2  | ppm  | ≥ 1000      | ≥ 5000     |
| O2   | %    | < 18.0 또는 > 23.5 | < 16.0 |
| NO2  | ppm  | ≥ 3         | ≥ 5        |
| SO2  | ppm  | ≥ 2         | ≥ 5        |
| O3   | ppm  | ≥ 0.06      | ≥ 0.12     |
| NH3  | ppm  | ≥ 25        | ≥ 35       |
| VOC  | ppm  | ≥ 0.5       | ≥ 1.0      |
| LEL  | %    | 임계치 미정의 — 알람 대상 제외 | |

---

## 8. 서버 실행 명령어

```bash
# DRF (8000)
cd drf-server && source .venv/bin/activate
python manage.py runserver 8000

# FastAPI HTTP 센서 수신 (8001)
cd fastapi-server
uvicorn main:app --port 8001 --reload

# FastAPI WebSocket jhh 작업본 (8002)
uvicorn websocket_jhh:app --port 8002 --reload

# 더미 데이터 전송
python dummy_sender.py
```

접속 URL: `http://localhost:8000/dashboard/jhh/`

---

## 9. 테스트 결과 요약

| 항목 | 결과 |
|------|------|
| DRF GasData 저장 | ✅ 201 응답 확인 |
| 알람 미발생 시 응답 크기 | ✅ 37 bytes (`alarms: []`) |
| 알람 발생 시 응답 크기 | ✅ ~257 bytes (alarms 포함) |
| FastAPI 8002 alarm Push | ✅ `POST /internal/alarm/ 200 OK` |
| FastAPI 8002 gas-snapshot Push | ✅ `POST /internal/gas-snapshot/ 200 OK` |
| Django admin AlarmRecord/Event 확인 | ✅ 레코드 생성 확인 |
| Event 병합 동작 | ✅ 활성 Event 존재 시 AlarmRecord만 추가 |
| 브라우저 WS 연결 포트 | ✅ 8002 (websocket_jhh.js) |
| 브라우저 알람 팝업 | ✅ data.alarms 수신 시 AlarmPopup.show() 동작 |
| 이벤트 현황 패널 색상 | ✅ 위험=빨간 점, 주의=노란 점 구분 표시 |
| 이벤트 현황 패널 설명 | ✅ "CO 임계치 초과 (273.0 ppm)" 한글 표시 |
| 작업자 위치 맵 반영 | ✅ worker_positions 객체→배열 변환 후 MapPanel 정상 동작 |
