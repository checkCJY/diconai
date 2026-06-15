# JSON 필드 명세서 — 데이터 흐름별 페이로드 정의

> 마지막 갱신: 2026-05-07
> 버전: 1.0.0
> 대상 독자: 신규 합류 개발자 / 외부 평가자 / 프론트엔드 개발자

---

## 0. 개요

본 문서는 diconai 시스템 내 **3단계 데이터 흐름**에서 송수신되는 JSON 페이로드 필드를 정리한 산출물이다.

```
Dummy(IoT)  ──HTTPS POST──▶  FastAPI  ──HTTPS POST──▶  DRF
                                │
                                └──WebSocket──▶  FrontEnd
```

### 검증 책임 분리

| 서버 | 검증 도구 | 위치 |
|---|---|---|
| **FastAPI** | **Pydantic BaseModel** | [`fastapi-server/*/schemas/*.py`](../fastapi-server/) |
| **DRF** | **DRF Serializer** | [`drf-server/apps/*/serializers/*.py`](../drf-server/apps/) |

- FastAPI는 라우터 함수 시그니처에 Pydantic 모델을 지정하면 **자동으로 422 응답**을 반환한다.
- DRF는 `serializer.is_valid(raise_exception=True)` 호출 시 **400 응답**을 반환한다.

---

## 1단계 — Dummy → FastAPI (센서 수신)

> **검증 도구: Pydantic BaseModel**
> 검증 실패 시 HTTP 422 (Unprocessable Entity) 자동 응답

### 1-1. 가스 기기 식별 정보 (부팅 시 1회)

- **엔드포인트**: `POST /api/sensors/info`
- **검증 스키마**: [`DeviceInfoPayload`](../fastapi-server/gas/schemas/gas.py)

| 필드 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `device_id` | str | ✅ | - | 장비 하드웨어 식별자 (MAC) |
| `device_name` | str | ✅ | - | 장비 이름 (현재 MAC과 동일) |
| `software_version` | str | ✅ | - | 펌웨어 버전 |
| `location` | object | ✅ | `{x: float, y: float}` | 설비 도면 픽셀 좌표 |

```json
{
  "device_id": "63200c3afd12",
  "device_name": "63200c3afd12",
  "software_version": "1.0.1",
  "location": { "x": 140, "y": 160 }
}
```

### 1-2. 가스 측정값 (1초 주기)

- **엔드포인트**: `POST /api/sensors/gas`
- **검증 스키마**: [`GasDataPayload`](../fastapi-server/gas/schemas/gas.py)

| 필드 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `timestamp` | datetime | ✅ | timezone-aware (naive는 UTC로 변환) | 측정 시각 (ISO 8601) |
| `device_id` | str | ✅ | - | 장비 식별자 |
| `device_name` | str | ✅ | - | 장비 이름 |
| `location` | object | ✅ | `{x, y}` | 센서 좌표 |
| `o2` | float | ✅ | `0 ≤ x ≤ 100` | 산소 (%) |
| `co` | float | ✅ | `≥ 0` | 일산화탄소 (ppm) |
| `co2` | float | ✅ | `≥ 0` | 이산화탄소 (ppm) |
| `h2s` | float | ✅ | `≥ 0` | 황화수소 (ppm) |
| `lel` | float | ✅ | `0 ≤ x ≤ 100` | 폭발하한계 (%) — 임계치 미정의 |
| `no2` | float | ✅ | `≥ 0` | 이산화질소 (ppm) |
| `so2` | float | ✅ | `≥ 0` | 이산화황 (ppm) |
| `o3` | float | ✅ | `≥ 0` | 오존 (ppm) |
| `nh3` | float | ✅ | `≥ 0` | 암모니아 (ppm) |
| `voc` | float | ✅ | `≥ 0` | 휘발성유기화합물 (ppm) |
| `status` | str | ❌ | `normal/warning/danger` | **수신 무시** — 서버에서 재계산 |

> **Pydantic 후처리**: `model_validator(mode="after")`에서 `status`를 가스 임계치 기반으로 재계산해 덮어쓴다.

```json
{
  "timestamp": "2026-05-07T08:00:00+00:00",
  "device_id": "63200c3afd12",
  "device_name": "63200c3afd12",
  "location": { "x": 140, "y": 160 },
  "co": 18, "h2s": 4, "co2": 720, "o2": 20.4, "lel": 2,
  "no2": 1.2, "so2": 0.8, "o3": 0.03, "nh3": 12, "voc": 0.21,
  "status": "normal"
}
```

### 1-3. 전력 ON/OFF 스냅샷

- **엔드포인트**: `POST /api/power/onoff`
- **검증 스키마**: [`PowerOnOffPayload`](../fastapi-server/power/schemas/power.py)

| 필드 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `device_id` | str | ✅ | `len ≤ 50` | 장비 식별자 |
| `slave01`~`slave72` | int | ✅ | `0 ≤ x ≤ 255` | 16채널 ON/OFF (255=ON, 0=OFF) |

> **채널 키**: `slave01, slave02, slave11, slave12, slave21, slave22, slave31, slave32, slave41, slave42, slave51, slave52, slave61, slave62, slave71, slave72` (총 16개)

```json
{
  "device_id": "63200c3afd12",
  "slave01": 255, "slave02": 0,
  "slave11": 255, "slave12": 255,
  "slave21": 0,   "slave22": 255,
  "slave31": 255, "slave32": 0,
  "slave41": 255, "slave42": 255,
  "slave51": 0,   "slave52": 255,
  "slave61": 255, "slave62": 0,
  "slave71": 255, "slave72": 255
}
```

### 1-4. 전력 측정값 (전류 / 전압 / 전력)

- **엔드포인트**:
  - `POST /api/power/current` (단위: A)
  - `POST /api/power/voltage` (단위: V)
  - `POST /api/power/watt` (단위: W)
- **검증 스키마**: [`PowerCurrentPayload`](../fastapi-server/power/schemas/power.py) / `PowerVoltagePayload` / `PowerWattPayload`

| 필드 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `device_id` | str | ✅ | `len ≤ 50` | 장비 식별자 |
| `slave01`~`slave72` | float | ✅ | `≥ -1` | 16채널 측정값 (`-1` = 통신 불능) |

```json
{
  "device_id": "63200c3afd12",
  "slave01": 12.5, "slave02": 0,    "slave11": 24,
  "slave12": -1,   "slave21": 8,    "slave22": 15,
  "slave31": 22,   "slave32": 0,    "slave41": 18,
  "slave42": 30,   "slave51": 4,    "slave52": 11,
  "slave61": 26,   "slave62": 0,    "slave71": 19,
  "slave72": 13
}
```

### 1-5. 작업자 위치 (배열)

- **엔드포인트**: `POST /api/positioning/receive`
- **검증 스키마**: [`WorkerPositionSchema`](../fastapi-server/positioning/schemas/position.py)

| 필드 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `worker_id` | int | ✅ | - | 작업자 ID |
| `worker_name` | str | ✅ | - | 작업자 이름 |
| `facility_id` | int | ✅ | - | 설비 ID |
| `x` | float | ✅ | `≥ 0` | X 좌표 (px) |
| `y` | float | ✅ | `≥ 0` | Y 좌표 (px) |
| `movement_status` | str | ❌ | default `"moving"` | 이동 상태 |
| `measured_at` | datetime | ✅ | ISO 8601 | 측정 시각 |
| `node_id` | str \| null | ❌ | default `null` | 측위 노드 device_id (예: `"NODE-001"`). 펌웨어 갱신 전 `null` |

> **루트 타입**: 배열 — `list[WorkerPositionSchema]`

```json
[
  {
    "worker_id": 1,
    "worker_name": "작업자 A",
    "facility_id": 1,
    "x": 150.32,
    "y": 120.18,
    "movement_status": "moving",
    "measured_at": "2026-05-07T08:00:00+00:00"
  }
]
```

---

## 2단계 — FastAPI → FrontEnd (WebSocket Broadcast)

> **검증 도구: 없음** (송신 전용)
> 페이로드 조립부에서 직접 `dict`를 구성해 `send_json()`으로 송신.

### 2-1. 메인 통합 스트림 (`WS /ws/sensors/`)

- **주기**: `BROADCAST_INTERVAL_SEC` (기본 5초, [`core/config.py`](../fastapi-server/core/config.py))
- **조립부**: [`build_broadcast_payload`](../fastapi-server/websocket/services/broadcast.py)

| 필드 | 타입 | 설명 |
|---|---|---|
| `timestamp` | str | 페이로드 조립 시각 (ISO 8601) |
| `total_power_kw` | float \| null | 16채널 합산 전력 (kW). stale 시 `null` |
| `power_change_pct` | float \| null | 직전 틱 대비 증감률 (%) |
| `equipment` | array | 16개 설비 채널 현황 (아래 표) |
| `power_loading` | bool | 전력 데이터 로딩 중(stale) 여부 |
| `gas_loading` | bool | 가스 데이터 로딩 중(stale) 여부 |
| `ai_power_equipment` | str \| null | AI 예측 — 최대 부하 설비명 (현재 `equipment` 첫 채널명, 미수신 시 `null`) |
| `ai_eta_min` | int \| null | AI 예측 — 도달 ETA (분). **모델 연동 전까지 항상 `null`** |
| `ai_max_load_kw` | float \| null | AI 예측 — 최대 부하 (kW). **모델 연동 전까지 항상 `null`** |
| `ai_max_load_pct` | int \| null | AI 예측 — 최대 부하 비율 (%). **모델 연동 전까지 항상 `null`** |
| `alarms` | array | 주기 broadcast에서는 **항상 빈 배열** — 실제 알람은 `alarm_flush_loop`이 별도 즉시 송신 (아래 표는 그 항목 구조) |
| `co`~`voc` | float | 가스 9종 측정값 (스프레드) |
| `co_risk`~`voc_risk` | str | 가스별 위험도 (스프레드) |

> 작업자 위치(`worker_positions`)는 이 스트림에서 **제거**되어 위치 전용 스트림(2-2 `/ws/positions/`, 1초 주기)이 단독 담당함. 5초 broadcast에 포함 시 1초 갱신을 덮어써 마커 순간이동이 발생했기 때문.

**`equipment[]` 항목 구조**:

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | str | 설비명 (예: `"압연기"`) |
| `watt` | float \| null | 전력 (W) |
| `voltage` | float \| null | 전압 (V) |
| `current` | float \| null | 전류 (A) |
| `onoff` | bool \| null | 통전 여부 |
| `sensor_status` | str | `"active"` / `"comm_failure"` |
| `risk_level` | str | `"normal"` / `"warning"` / `"danger"` |

**`alarms[]` 항목 구조** (Celery → `/internal/alarms/push/` → 큐 적재 → `alarm_flush_loop`이 송신):

| 필드 | 타입 | 설명 |
|---|---|---|
| `alarm_type` | str | `"gas_threshold"` / `"power_overload"` / `"geofence_intrusion"` / `"gas_anomaly_ai"` / `"power_anomaly_ai"` ([`AlarmType`](../drf-server/apps/core/constants.py)) |
| `risk_level` | str | `"warning"` / `"danger"` |
| `source_label` | str | 알람 출처 라벨 |
| `summary` | str | 알람 요약 메시지 |
| `is_new_event` | bool | 신규 이벤트 여부 |
| `event_id` | int \| null | DRF Event PK |
| `gas_type` | str \| null | 가스 알람 시 가스 종류 |
| `measured_value` | float \| null | 측정값 |
| `threshold_value` | float \| null | 임계값 |
| `worker_id` | int \| null | 지오펜스 알람 시 타겟 작업자 |

> 아래 예시의 `alarms[]`는 **항목 구조 참고용**임. 주기 broadcast 페이로드의 `alarms`는 실제로는 항상 `[]`이고, 채워진 알람은 `alarm_flush_loop`이 같은 `/ws/sensors/`로 별도 송신함.

```json
{
  "timestamp": "2026-05-07T17:00:00.123456+00:00",
  "total_power_kw": 18.42,
  "power_change_pct": 1.3,
  "equipment": [
    {
      "name": "압연기", "watt": 1820, "voltage": 220, "current": 8,
      "onoff": true, "sensor_status": "active", "risk_level": "normal"
    }
  ],
  "power_loading": false,
  "gas_loading": false,
  "ai_power_equipment": "압연기",
  "ai_eta_min": null,
  "ai_max_load_kw": null,
  "ai_max_load_pct": null,
  "alarms": [
    {
      "alarm_type": "gas_threshold", "risk_level": "danger",
      "source_label": "가스센서 #63200c3afd12",
      "summary": "CO 농도 위험 (210ppm)",
      "is_new_event": true, "event_id": 1234,
      "gas_type": "co", "measured_value": 210, "threshold_value": 200
    }
  ],
  "co": 18, "h2s": 4, "co2": 720, "o2": 20.4,
  "no2": 1.2, "so2": 0.8, "o3": 0.03, "nh3": 12, "voc": 0.21,
  "co_risk": "normal", "h2s_risk": "normal", "co2_risk": "normal",
  "o2_risk": "normal", "no2_risk": "normal", "so2_risk": "normal",
  "o3_risk": "normal", "nh3_risk": "normal", "voc_risk": "normal"
}
```

### 2-2. 위치 전용 스트림 (`WS /ws/positions/`)

- **주기**: 1초 고정
- **조립부**: [`position_stream`](../fastapi-server/positioning/routers/position_router.py)

| 필드 | 타입 | 설명 |
|---|---|---|
| `worker_positions` | array | 작업자 배열 (worker_id 포함) |

```json
{
  "worker_positions": [
    {
      "worker_id": 1, "x": 150.32, "y": 120.18,
      "facility_id": 1, "worker_name": "작업자 A",
      "movement_status": "moving",
      "updated_at": "2026-05-07T08:00:00+00:00",
      "risk_level": "normal", "zone_name": null
    }
  ]
}
```

### 2-3. 작업자 개인 알림 (`WS /ws/worker/{user_id}/`)

- **트리거**: 지오펜스 진입 시에만 송신
- **조립부**: [`push_alarm`](../fastapi-server/internal/routers/alarm_router.py)

| 필드 | 타입 | 설명 |
|---|---|---|
| `type` | str | 고정값 `"worker_alert"` |
| `alarm_type` | str | `"geofence_intrusion"` |
| 그 외 | - | 2-1의 `alarms[]` 항목과 동일 |

```json
{
  "type": "worker_alert",
  "alarm_type": "geofence_intrusion",
  "risk_level": "danger",
  "source_label": "지오펜스 진입",
  "summary": "위험구역 진입 감지",
  "is_new_event": true,
  "event_id": 5678,
  "worker_id": 1
}
```

---

## 3단계 — FastAPI → DRF (영속화)

> **검증 도구: DRF Serializer**
> 검증 실패 시 HTTP 400 (Bad Request) 응답

### 3-1. 가스 데이터 저장

- **엔드포인트**: `POST /api/monitoring/gas/`
- **검증 시리얼라이저**: [`GasDataCreateSerializer`](../drf-server/apps/monitoring/serializers/gas_data.py)
- **조립부 (FastAPI)**: [`process_gas_data`](../fastapi-server/gas/services/gas_service.py)

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `device_id` | str | ✅ | `write_only` — `GasSensor` FK 조회 키 |
| `measured_at` | datetime | ✅ | 측정 시각 |
| `co`, `h2s`, `co2`, `o2`, `no2`, `so2`, `o3`, `nh3`, `voc` | float | ✅ | 가스 9종 측정값 (lel은 모델 컬럼 없음) |
| `co_risk`, `h2s_risk`, `co2_risk`, `o2_risk`, `no2_risk`, `so2_risk`, `o3_risk`, `nh3_risk`, `voc_risk` | str | ✅ | 가스별 위험도 (`normal`/`warning`/`danger`) |
| `raw_payload` | object | ✅ | FastAPI가 받은 원본 페이로드 (lel 포함) |

> **Serializer 후처리**: `validate()`에서 `device_id`로 `GasSensor` 조회 후 `gas_sensor` FK로 변환. `create()`에서 `trigger_gas_alarms()` 호출하여 Celery 알람 태스크 트리거.

```json
{
  "device_id": "63200c3afd12",
  "measured_at": "2026-05-07T08:00:00+00:00",
  "co": 18, "h2s": 4, "co2": 720, "o2": 20.4,
  "no2": 1.2, "so2": 0.8, "o3": 0.03, "nh3": 12, "voc": 0.21,
  "co_risk": "normal", "h2s_risk": "normal", "co2_risk": "normal",
  "o2_risk": "normal", "no2_risk": "normal", "so2_risk": "normal",
  "o3_risk": "normal", "nh3_risk": "normal", "voc_risk": "normal",
  "raw_payload": {
    "timestamp": "2026-05-07T08:00:00+00:00",
    "device_id": "63200c3afd12",
    "...": "GasDataPayload 원본 전체 (lel 포함)"
  }
}
```

### 3-2. 전력 ON/OFF 이벤트 저장

- **엔드포인트**: `POST /api/monitoring/power/event/`
- **검증 시리얼라이저**: [`PowerEventIngestSerializer`](../drf-server/apps/monitoring/serializers/power_data.py)
- **조립부 (FastAPI)**: [`recv_onoff`](../fastapi-server/power/routers/power_router.py)

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `device_id` | str | ✅ | `len ≤ 50` — `PowerDevice` FK 조회 키 |
| `measured_at` | datetime | ✅ | 측정 시각 |
| `snapshot` | object | ✅ | `{"1": bool, ..., "16": bool}` — 채널 번호 문자열 키 |

> **Serializer 후처리**: `create()`에서 직전 스냅샷과 비교해 `changed_channels` 자동 계산.

```json
{
  "device_id": "63200c3afd12",
  "measured_at": "2026-05-07T08:00:00+00:00",
  "snapshot": {
    "1": true, "2": false, "3": true, "4": true,
    "5": false, "6": true, "7": true, "8": false,
    "9": true, "10": true, "11": false, "12": true,
    "13": true, "14": false, "15": true, "16": true
  }
}
```

### 3-3. 전력 측정값 일괄 저장

- **엔드포인트**: `POST /api/monitoring/power/data/`
- **검증 시리얼라이저**: [`PowerDataBulkIngestSerializer`](../drf-server/apps/monitoring/serializers/power_data.py)
- **조립부 (FastAPI)**: [`recv_current/voltage/watt`](../fastapi-server/power/routers/power_router.py)

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `device_id` | str | ✅ | `len ≤ 50` |
| `measured_at` | datetime | ✅ | 측정 시각 |
| `data_type` | str | ✅ | `current` / `voltage` / `watt` |
| `channels` | array | ✅ | 16채널 측정값 배열 (아래 표) |

**`channels[]` 항목 구조**:

| 필드 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `channel` | int | ✅ | `1 ≤ x ≤ 16` | 채널 번호 |
| `value` | float \| null | ❌ | default `null` | 측정값 (`null` = 통신 불능) |
| `sensor_status` | str | ❌ | default `"active"` | `"active"` / `"comm_failure"` |
| `risk_level` | str | ❌ | default `"normal"` | `"normal"` / `"warning"` / `"danger"` |

> **Serializer 후처리**: `create()`에서 `bulk_create(ignore_conflicts=True)`로 16채널 일괄 INSERT 후 `trigger_power_alarms()` 호출.

```json
{
  "device_id": "63200c3afd12",
  "measured_at": "2026-05-07T08:00:00+00:00",
  "data_type": "watt",
  "channels": [
    { "channel": 1, "value": 1820, "sensor_status": "active",       "risk_level": "normal" },
    { "channel": 2, "value": null, "sensor_status": "comm_failure", "risk_level": "normal" },
    { "channel": 3, "value": 2400, "sensor_status": "active",       "risk_level": "warning" }
  ]
}
```

### 3-4. 작업자 위치 저장

- **엔드포인트**: `POST /api/positioning/receive/`
- **검증 시리얼라이저**: [`WorkerPositionReceiveSerializer`](../drf-server/apps/positioning/serializers/serializers.py)
- **조립부 (FastAPI)**: [`save_positions_to_drf`](../fastapi-server/positioning/services/position_service.py)

| 필드 | 타입 | 필수 | 제약 | 설명 |
|---|---|---|---|---|
| `worker_id` | int | ✅ | - | 작업자 ID |
| `facility_id` | int | ✅ | - | 설비 ID |
| `x` | float | ✅ | `≥ 0` | X 좌표 |
| `y` | float | ✅ | `≥ 0` | Y 좌표 |
| `movement_status` | str | ❌ | `moving/stationary/idle`, default `moving` | 이동 상태 |
| `measured_at` | datetime | ✅ | - | 측정 시각 |
| `node_id` | str \| null | ❌ | `max_length=50`, default `null` | 측위 노드 device_id (예: `"NODE-001"`) |

> **루트 타입**: 배열. `worker_name`은 1단계와 달리 **포함되지 않음** (DRF는 `worker_id`로 조회).

```json
[
  {
    "worker_id": 1,
    "facility_id": 1,
    "x": 150.32,
    "y": 120.18,
    "movement_status": "moving",
    "measured_at": "2026-05-07T08:00:00+00:00"
  }
]
```

**응답 페이로드**:
```json
{
  "received": true,
  "saved": 0,
  "statuses": [
    { "worker_id": 1, "risk_level": "normal", "zone_name": null }
  ]
}
```

---

## 부록 A — 검증 매트릭스

| 단계 | 엔드포인트 | 검증 도구 | 검증 클래스 | 실패 응답 |
|---|---|---|---|---|
| 1 | `POST /api/sensors/info` | Pydantic | `DeviceInfoPayload` | 422 |
| 1 | `POST /api/sensors/gas` | Pydantic | `GasDataPayload` | 422 |
| 1 | `POST /api/power/onoff` | Pydantic | `PowerOnOffPayload` | 422 |
| 1 | `POST /api/power/current` | Pydantic | `PowerCurrentPayload` | 422 |
| 1 | `POST /api/power/voltage` | Pydantic | `PowerVoltagePayload` | 422 |
| 1 | `POST /api/power/watt` | Pydantic | `PowerWattPayload` | 422 |
| 1 | `POST /api/positioning/receive` | Pydantic | `WorkerPositionSchema` | 422 |
| 2 | `WS /ws/sensors/` | — | (송신 전용) | — |
| 2 | `WS /ws/positions/` | — | (송신 전용) | — |
| 2 | `WS /ws/worker/{user_id}/` | — | (송신 전용) | — |
| 3 | `POST /api/monitoring/gas/` | DRF Serializer | `GasDataCreateSerializer` | 400 |
| 3 | `POST /api/monitoring/power/event/` | DRF Serializer | `PowerEventIngestSerializer` | 400 |
| 3 | `POST /api/monitoring/power/data/` | DRF Serializer | `PowerDataBulkIngestSerializer` | 400 |
| 3 | `POST /api/positioning/receive/` | DRF Serializer | `WorkerPositionReceiveSerializer` | 400 |

---

## 부록 B — 검증 패턴 비교

### Pydantic (FastAPI)

```python
from pydantic import BaseModel, Field, field_validator

class GasDataPayload(BaseModel):
    o2: float = Field(ge=0, le=100)

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone_aware(cls, v): ...
```

- 라우터 함수 시그니처에 타입 힌트로 지정 → 자동 검증
- `Field(ge=, le=, max_length=)` 로 제약 표현
- `@field_validator` / `@model_validator`로 커스텀 검증

### DRF Serializer

```python
from rest_framework import serializers

class WorkerPositionReceiveSerializer(serializers.Serializer):
    x = serializers.FloatField(min_value=0)
    movement_status = serializers.ChoiceField(
        choices=["moving", "stationary", "idle"], default="moving"
    )

    def validate(self, attrs): ...
    def create(self, validated_data): ...
```

- 뷰에서 명시적으로 `serializer.is_valid(raise_exception=True)` 호출
- `min_value=, max_length=, choices=` 로 제약 표현
- `validate_<field>()` / `validate()` / `create()` 로 후처리 분리

---

## 관련 문서

- [API 명세서](api_specification.md) — 인증·WebSocket·IoT 통합 가이드
- [URL 구조](url-structure.md) — 전체 URL 라우팅
- [개발 컨벤션](dev_convention.md) — 코딩 스타일
