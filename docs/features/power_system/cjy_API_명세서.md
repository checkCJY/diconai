# 전력 시스템 — API 명세서

> FastAPI 수신 엔드포인트 4개 + DRF 저장 엔드포인트 2개

---

## FastAPI Endpoints

### POST /api/power/onoff

16채널 ON/OFF 상태 스냅샷을 수신하여 DRF PowerEvent로 저장

**인증:** 없음 (내부 서비스 전용)

**Request Body**

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|------|------|------|
| device_id | string | Y | max_length=50 | 하드웨어 식별자 (MAC 주소 형식) |
| slave01 | integer | Y | 0 or 255 | CH1 ON/OFF (255=ON, 0=OFF) |
| slave02 | integer | Y | 0 or 255 | CH2 |
| slave11 | integer | Y | 0 or 255 | CH3 |
| slave12 | integer | Y | 0 or 255 | CH4 |
| slave21 | integer | Y | 0 or 255 | CH5 |
| slave22 | integer | Y | 0 or 255 | CH6 |
| slave31 | integer | Y | 0 or 255 | CH7 |
| slave32 | integer | Y | 0 or 255 | CH8 |
| slave41 | integer | Y | 0 or 255 | CH9 |
| slave42 | integer | Y | 0 or 255 | CH10 |
| slave51 | integer | Y | 0 or 255 | CH11 |
| slave52 | integer | Y | 0 or 255 | CH12 |
| slave61 | integer | Y | 0 or 255 | CH13 |
| slave62 | integer | Y | 0 or 255 | CH14 |
| slave71 | integer | Y | 0 or 255 | CH15 |
| slave72 | integer | Y | 0 or 255 | CH16 |

**Request 예시**
```json
{
  "device_id": "63200c3afd12",
  "slave01": 255,
  "slave02": 0,
  "slave11": 255,
  "slave12": 255,
  "slave21": 0,
  "slave22": 0,
  "slave31": 255,
  "slave32": 0,
  "slave41": 255,
  "slave42": 255,
  "slave51": 0,
  "slave52": 255,
  "slave61": 0,
  "slave62": 0,
  "slave71": 255,
  "slave72": 255
}
```

**Response**

| 상태코드 | Body | 설명 |
|----------|------|------|
| 201 | `{"id": 1}` | PowerEvent 저장 성공, id는 DRF DB 기준 |
| 422 | Pydantic ValidationError | 필드 타입 오류 또는 범위 초과 |
| 502 | `{"detail": "DRF 502: ..."}` | DRF 서버 오류 |
| 504 | `{"detail": "DRF 응답 타임아웃"}` | DRF 5초 응답 없음 |

---

### POST /api/power/current

16채널 전류(A) 측정값 수신

**인증:** 없음 (내부 서비스 전용)

**Request Body**

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|------|------|------|
| device_id | string | Y | max_length=50 | 하드웨어 식별자 |
| slave01~slave72 | float | Y | >= -1 | 전류값(A). -1은 통신 불능(프로토콜 규정) |

**Request 예시**
```json
{
  "device_id": "63200c3afd12",
  "slave01": 12.5,
  "slave02": -1,
  "slave11": 8.3,
  "slave12": 15.0,
  "slave21": 0.0,
  "slave22": 22.1,
  "slave31": 9.7,
  "slave32": -1,
  "slave41": 11.2,
  "slave42": 6.8,
  "slave51": 18.4,
  "slave52": 3.1,
  "slave61": 0.0,
  "slave62": 25.0,
  "slave71": 7.6,
  "slave72": 14.3
}
```

**Response**

| 상태코드 | Body | 설명 |
|----------|------|------|
| 201 | `{"created": 16}` | 16채널 PowerData 저장 성공 |
| 422 | Pydantic ValidationError | 필드 타입 오류 또는 -1 미만 값 |
| 502 | `{"detail": "DRF 502: ..."}` | DRF 서버 오류 |
| 504 | `{"detail": "DRF 응답 타임아웃"}` | DRF 5초 응답 없음 |

---

### POST /api/power/voltage

16채널 전압(V) 측정값 수신. Request/Response 구조는 `/api/power/current` 와 동일.

**단위:** V / **정상 범위:** 215~225V (더미 기준)

---

### POST /api/power/watt

16채널 전력(W) 측정값 수신. Request/Response 구조는 `/api/power/current` 와 동일.

**단위:** W / **정상 범위:** 50~5000W (더미 기준)

---

## DRF Endpoints

> FastAPI가 내부적으로 호출하는 엔드포인트. 직접 호출도 가능(테스트 및 개발용)

### POST /monitoring/api/power/event/

PowerEvent(ON/OFF 스냅샷) 저장

**인증:** 없음 (AllowAny — 추후 서비스 토큰 정책 결정 후 변경 예정)

**Request Body**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| device_id | string | Y | PowerDevice.device_id (DB에 등록된 장비만 허용) |
| measured_at | string (ISO8601 UTC) | Y | 장치 측정 시각. FastAPI가 주입. 예: `2026-04-22T10:00:00+00:00` |
| snapshot | object | Y | `{"1": bool, ..., "16": bool}` 형식. 키: 1~16 문자열, 값: bool |

**Request 예시**
```json
{
  "device_id": "63200c3afd12",
  "measured_at": "2026-04-22T10:00:00+00:00",
  "snapshot": {
    "1": true, "2": false, "3": true, "4": false,
    "5": true, "6": false, "7": true, "8": false,
    "9": true, "10": false, "11": true, "12": false,
    "13": true, "14": false, "15": true, "16": false
  }
}
```

**Response**

| 상태코드 | Body | 설명 |
|----------|------|------|
| 201 | `{"id": 1}` | 저장 성공 |
| 400 | DRF ValidationError | snapshot 구조 오류, measured_at 형식 오류 |
| 500 | - | device_id에 해당하는 PowerDevice 미등록 시 |

---

### POST /monitoring/api/power/data/

PowerData(전류/전압/전력) 16채널 일괄 저장

**인증:** 없음 (AllowAny — 추후 서비스 토큰 정책 결정 후 변경 예정)

**Request Body**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| device_id | string | Y | PowerDevice.device_id |
| measured_at | string (ISO8601 UTC) | Y | 장치 측정 시각 |
| data_type | string | Y | `"current"` / `"voltage"` / `"watt"` |
| channels | array | Y | 채널별 측정값 리스트 (아래 참고) |

**channels 배열 항목**

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|------|------|------|
| channel | integer | Y | 1~16 | 채널 번호 |
| value | float | Y | >= -1 | 측정값. -1은 통신 불능 |
| risk_level | string | N | normal/warning/danger | 기본값: normal |

**Request 예시**
```json
{
  "device_id": "63200c3afd12",
  "measured_at": "2026-04-22T10:00:00+00:00",
  "data_type": "current",
  "channels": [
    {"channel": 1, "value": 12.5, "risk_level": "normal"},
    {"channel": 2, "value": -1,   "risk_level": "normal"},
    {"channel": 3, "value": 8.3,  "risk_level": "normal"}
  ]
}
```

**Response**

| 상태코드 | Body | 설명 |
|----------|------|------|
| 201 | `{"created": 16}` | 저장 성공 (동일 시각 중복 전송 시 uq 충돌 무시, 실제 저장 수 반환) |
| 400 | DRF ValidationError | data_type 오류, channel 범위 초과, value -1 미만 등 |
| 500 | - | device_id 미등록 |
