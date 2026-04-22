# 가스 센서 HTTP 수신 파이프라인

## 목적

실제 가스 센서 장비(에어위드)가 HTTP로 전송하는 측정값을 FastAPI가 수신·검증한 뒤 DRF 서버로 넘기기 위한 파이프라인을 구축한다.

장비 연동 전 단계에서는 `dummy_sender.py`로 실제 장비 전송을 시뮬레이션한다.

---

## 전체 흐름

```
[에어위드 센서 장비]           실제 장비 연동 시
        ↓  (또는)
[dummy_sender.py]              장비 없이 테스트 시
        ↓
        POST /api/sensors/info   (부팅 시 1회 — 기기 식별 정보)
        POST /api/sensors/gas    (1초마다 — 가스 측정값 10종)
        ↓
[FastAPI main.py]
  - Pydantic 스키마로 페이로드 검증
  - status 서버 재계산 (센서 전송값 무시, 임계치 기준 직접 판정)
        ↓
  (TODO) DRF POST → DB 저장 · 알람 판정
```

---

## 파일별 역할

| 파일 | 역할 |
|------|------|
| `gas_thresholds.py` | 가스별 임계치 기준값 + `calculate_gas_status()` 판정 함수 |
| `schemas.py` | Pydantic 수신 스키마 (`DeviceInfoPayload`, `GasDataPayload`) |
| `main.py` | FastAPI 엔드포인트 (`/api/sensors/info`, `/api/sensors/gas`) |
| `dummy_sender.py` | 장비 시뮬레이션 — 더미 데이터 생성 후 FastAPI로 전송 |

---

## 엔드포인트

### `POST /api/sensors/info` — 기기 정보

장비 부팅 시 1회 전송. 기기 식별 및 지오펜스 좌표 등록용.

**요청 바디**
```json
{
  "device_id": "63200c3afd12",
  "device_name": "63200c3afd12",
  "software_version": "1.0.1",
  "location": { "x": 140, "y": 160 }
}
```

**응답**
```json
{ "received": true, "device_id": "63200c3afd12" }
```

---

### `POST /api/sensors/gas` — 가스 측정값

1초마다 전송. 가스 10종(9종 + LEL) 측정값.

**요청 바디**
```json
{
  "timestamp": "2026-04-21T15:00:00",
  "device_id": "63200c3afd12",
  "device_name": "63200c3afd12",
  "location": { "x": 140, "y": 160 },
  "o2": 20.15,
  "co": 12,
  "co2": 560,
  "h2s": 4,
  "lel": 2,
  "no2": 1.2,
  "so2": 0.8,
  "o3": 0.02,
  "nh3": 8,
  "voc": 0.3,
  "status": "normal"
}
```

> **주의**: `status`는 센서 전송값을 그대로 사용하지 않는다.  
> FastAPI가 수신된 가스값으로 서버에서 직접 재계산하여 덮어쓴다.  
> 센서 오작동 또는 조작으로 인한 잘못된 상태값을 방어하기 위함.

**응답**
```json
{ "received": true, "device_id": "63200c3afd12", "status": "normal" }
```

---

## 가스 임계치 기준

출처: 가스별 임계치 기준 이미지 문서 (디코나이 내부 문서)

| 가스 | 단위 | 정상 상한 | 주의 상한 | 비고 |
|------|------|-----------|-----------|------|
| CO   | ppm  | 25        | 200       | |
| H₂S  | ppm  | 10        | 15        | |
| CO₂  | ppm  | 1,000     | 5,000     | |
| O₂   | %    | 18.0 ~ 23.5 (정상 범위) | 16.0 미만 시 주의 | 낮을수록 위험 |
| NO₂  | ppm  | 3         | 5         | |
| SO₂  | ppm  | 2         | 5         | |
| O₃   | ppm  | 0.06      | 0.12      | |
| NH₃  | ppm  | 25        | 35        | |
| VOC  | ppm  | 0.5       | 1.0       | |
| LEL  | %    | —         | —         | 임계치 미정의, 수집만 함 |

**상태 판정 규칙**

- `danger` : 하나라도 주의 상한 이상이면 즉시 반환
- `warning` : 하나라도 정상 상한 이상이면 반환
- `normal`  : 전체 정상

---

## 테스트 방법

### 1. FastAPI 서버 실행

```bash
cd fastapi-server
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

> COMMANDS.md의 기존 포트는 8001(websocket 전용)이고,  
> gas HTTP 수신은 `main.py`를 **8000**으로 실행한다.  
> 두 서버를 동시에 쓸 경우 포트를 분리해서 실행.

### 2. Swagger UI 확인

브라우저에서 `http://localhost:8000/docs` 접속 → 엔드포인트 목록 및 직접 테스트 가능.

### 3. 더미 데이터 전송

서버가 실행 중인 상태에서 별도 터미널로:

```bash
cd fastapi-server
source .venv/bin/activate
python dummy_sender.py
```

로그 예시:
```
2026-04-21 15:00:00 [INFO] === 더미 데이터 전송 시작 (위험 이벤트 확률: 10%) ===
2026-04-21 15:00:00 [INFO] [DEVICE_INFO] HTTP 200 | status=- | {...}
2026-04-21 15:00:00 [INFO] 가스 데이터 전송 시작 → http://localhost:8000/api/sensors/gas
2026-04-21 15:00:01 [INFO] [GAS] HTTP 200 | status=normal | {...}
2026-04-21 15:00:02 [INFO] [GAS] HTTP 200 | status=danger | {...}
```

### 4. curl로 단건 테스트

```bash
curl -X POST http://localhost:8000/api/sensors/gas \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-04-21T15:00:00",
    "device_id": "63200c3afd12",
    "device_name": "63200c3afd12",
    "location": {"x": 140, "y": 160},
    "o2": 20.0, "co": 300, "co2": 500,
    "h2s": 3, "lel": 1,
    "no2": 1.0, "so2": 0.5, "o3": 0.01,
    "nh3": 10, "voc": 0.2,
    "status": "normal"
  }'
```

`co: 300`이 주의 상한(200) 이상이므로 응답의 `status`는 `"danger"`로 재계산된다.

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `fastapi-server/gas_thresholds.py` | 임계치 상수 + 상태 판정 함수 |
| `fastapi-server/schemas.py` | Pydantic 스키마 |
| `fastapi-server/main.py` | 수신 엔드포인트 |
| `fastapi-server/dummy_sender.py` | 더미 전송 스크립트 |
| `fastapi-server/websocket.py` | 별도 — 대시보드용 WebSocket 스트리밍 (포트 8001) |
