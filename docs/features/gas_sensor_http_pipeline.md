# 가스 센서 HTTP 수신 파이프라인

## 목적

실제 가스 센서 장비(에어위드)가 HTTP로 전송하는 측정값을 FastAPI가 수신·검증한 뒤 DRF 서버로 넘겨 영속화하고, 위험 시 알람으로 연결하는 파이프라인.

장비 연동 전 단계에서는 `dummies/gas_dummy.py`로 실제 장비 전송을 시뮬레이션한다.

> 패키지 리팩토링 반영 — 과거 단일파일(`main.py`/`schemas.py`/`gas_thresholds.py`) 구조에서
> 도메인 패키지(`gas/routers`·`gas/schemas`·`gas/services`)로 분리됨. FastAPI는 `:8001`
> 단일 앱(`app.py`)으로 기동하며, 가스 HTTP 수신과 WebSocket이 같은 프로세스에 공존한다.

---

## 전체 흐름

```
[에어위드 센서 장비]           실제 장비 연동 시
        ↓  (또는)
[dummies/gas_dummy.py]         장비 없이 테스트 시
        ↓
        POST /api/sensors/info   (부팅 시 1회 — 기기 식별 정보)
        POST /api/sensors/gas    (1초마다 — 가스 측정값 10종: 9종 + LEL)
        ↓
[FastAPI :8001  gas/routers/gas_router.py]
  - gas/schemas/gas.py 의 Pydantic 스키마로 페이로드 검증
  - status 서버 재계산 (센서 전송값 무시, 임계치 기준 직접 판정)
        ↓
[gas/services/gas_service.py  process_gas_data]
  1. DRF 영속화 — POST /api/monitoring/gas/ (구현 완료)
  2. Redis 스냅샷 갱신 — 다음 WebSocket broadcast tick 에 브라우저로 전달
  3. warning/danger → DRF Celery 정적 룰 알람 트리거
  4. (AI) CP 게이트 통과 + IF 이상 적중 시 push_alarm 으로 실시간 알람 직접 push
     + forward_inference_e2e 로 ML 결과/AlarmRecord 비동기 저장
```

---

## 파일별 역할 (현재 구조)

| 파일 | 역할 |
|------|------|
| [`core/gas_thresholds.py`](../../fastapi-server/core/gas_thresholds.py) | `GAS_THRESHOLDS` 상수 + `evaluate_single_gas` / `calculate_individual_risks` / `calculate_gas_status` 판정 함수 |
| [`gas/schemas/gas.py`](../../fastapi-server/gas/schemas/gas.py) | Pydantic 수신/응답 스키마 (`DeviceInfoPayload`, `GasDataPayload`, `DeviceInfoResponse`, `GasDataResponse`) |
| [`gas/routers/gas_router.py`](../../fastapi-server/gas/routers/gas_router.py) | FastAPI 엔드포인트 (prefix `/api/sensors` → `/info`, `/gas`) |
| [`gas/services/gas_service.py`](../../fastapi-server/gas/services/gas_service.py) | `process_gas_data` — 검증 후 DRF 영속화 + Redis 스냅샷 + AI 추론/알람 |
| [`dummies/gas_dummy.py`](../../fastapi-server/dummies/gas_dummy.py) | 장비 시뮬레이션 — 더미 데이터 생성 후 FastAPI로 전송 |

---

## 엔드포인트

### `POST /api/sensors/info` — 기기 정보

장비 부팅 시 1회 전송. 기기 식별용. 수신 시 `device_id`를 Redis Set에 등록해
이후 가스 수신 단계에서 등록 여부를 DRF 블로킹 없이 즉시 판정한다.

**요청 바디**
```json
{
  "device_id": "63200c3afd12",
  "device_name": "63200c3afd12",
  "software_version": "1.0.1",
  "location": { "x": 140, "y": 160 }
}
```

**응답** (`DeviceInfoResponse`)
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

**응답** (`GasDataResponse`, `extra="allow"` — 가스별 `*_risk` 동적 포함)
```json
{
  "received": true,
  "device_id": "63200c3afd12",
  "status": "normal",
  "co_risk": "normal", "h2s_risk": "normal", "co2_risk": "normal",
  "o2_risk": "normal", "no2_risk": "normal", "so2_risk": "normal",
  "o3_risk": "normal", "nh3_risk": "normal", "voc_risk": "normal"
}
```

---

## 가스 임계치 기준

출처: 가스별 임계치 기준 이미지 문서 (디코나이 내부 문서). 코드 SoT: [`core/gas_thresholds.py`](../../fastapi-server/core/gas_thresholds.py) `GAS_THRESHOLDS`.

| 가스 | 단위 | `normal_max` | `warning_max` | 비고 |
|------|------|-----------|-----------|------|
| CO   | ppm  | 25        | 200       | |
| H₂S  | ppm  | 10        | 15        | |
| CO₂  | ppm  | 1,000     | 5,000     | |
| O₂   | %    | 18.0 ~ 23.5 (정상 범위) | `warning_min` 16.0 | 낮을수록 위험 |
| NO₂  | ppm  | 3         | 5         | |
| SO₂  | ppm  | 2         | 5         | |
| O₃   | ppm  | 0.06      | 0.12      | |
| NH₃  | ppm  | 25        | 35        | |
| VOC  | ppm  | 0.5       | 1.0       | |
| LEL  | %    | —         | —         | 임계치 미정의, 수집만 함 (판정 제외) |

**상태 판정 규칙** (`evaluate_single_gas` / `calculate_gas_status`)

- `danger` : 하나라도 `warning_max` 이상(O₂는 `warning_min` 미만)이면 즉시 반환
- `warning` : 하나라도 `normal_max` 이상(O₂는 정상 범위 밖)이면 반환
- `normal`  : 전체 정상
- LEL은 임계치 미정의이므로 판정에서 제외

---

## 테스트 방법

> 런타임은 Docker Compose 통합 환경 (`:8001` = FastAPI). 호스트에서 `uvicorn`을 직접
> 띄우지 않는다. 명령어 전체는 [docs/conventions/COMMANDS.md](../conventions/COMMANDS.md) 참조.

### 1. 통합 환경 기동

```bash
make up            # 전체 스택 기동 (drf:8000, fastapi:8001, redis, pg, celery, ...)
```

### 2. Swagger UI 확인

브라우저에서 `http://localhost:8001/docs` 접속 → 엔드포인트 목록 및 직접 테스트 가능.

### 3. 더미 데이터 전송

```bash
make dummies-start   # 가스·전력·위치 더미 동시 송출 (1초 주기)
make dummies-stop    # 중지
```

### 4. curl로 단건 테스트

```bash
curl -X POST http://localhost:8001/api/sensors/gas \
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

`co: 300`이 `warning_max`(200) 이상이므로 응답의 `status`는 `"danger"`로 재계산된다.

---

## 관련 문서

- [docs/specs/json_fields_specification.md](../specs/json_fields_specification.md) — 단계별 페이로드 정의(전체)
- [docs/ai/pipeline.md](../ai/pipeline.md) — 가스 AI(CP 게이트 → IF) 추론 흐름
- [docs/domains/websocket.md](../domains/websocket.md) — WebSocket broadcast 흐름
