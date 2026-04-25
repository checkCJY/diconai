# Phase 3 리팩토링 — FastAPI 서버 도메인 분리 및 통합

## 개요

기존에 `websocket.py`, `websocket_CJY.py`, `websocket_jhh.py`, `main.py` 등 역할이 혼재된 단일 파일 구조를,
`positioning/` 폴더의 패턴(routers / schemas / services)을 기준으로 도메인별 모듈로 분리했다.

---

## 변경 전 구조

```
fastapi-server/
├── main.py                      # 구 진입점 (power_system 라우터 + sensors 라우터)
├── websocket.py                 # jhh 기반 — 가스/전력/AI 더미 + worker_positions
├── websocket_CJY.py             # CJY 작업본 — 전력 실데이터 수신 + WS 브로드캐스트
├── websocket_jhh.py             # jhh 작업본 — 가스 알람 Push 수신 (/internal/*)
├── dummy_sender.py              # 가스 더미 전송 스크립트 (루트에 위치)
├── routers/
│   └── sensors.py               # 가스 센서 라우터 (구)
├── schemas/
│   └── sensors.py               # 가스 스키마 (구)
└── power_system/
    ├── schemas.py               # 전력 스키마 (구)
    ├── router_cjy.py            # 전력 라우터 (구, _cjy 접미사)
    └── power_dummy_sender.py    # 전력 더미 전송 스크립트 (구)
```

### 구조의 문제점

| 문제 | 설명 |
|------|------|
| 파일 난립 | websocket 3개 파일이 각자 `app = FastAPI()` 를 선언, 동시에 실행 불가 |
| 내부 HTTP Push | `websocket_jhh.py`가 `/internal/alarm/`, `/internal/gas-snapshot/` 엔드포인트를 두어, 같은 프로세스 안에서 HTTP 왕복 발생 |
| 명명 불일치 | `router_cjy.py`, `_cjy` 접미사 등 작업자명이 파일명에 포함 |
| 더미 스크립트 위치 | 루트 + power_system/ 에 분산 |

---

## 변경 후 구조

```
fastapi-server/
├── app.py                       # 통합 진입점 — 모든 라우터 등록
├── core/
│   ├── config.py                # 설정 (DRF_BASE_URL 등)
│   └── gas_thresholds.py        # 가스 임계치 계산 공통 로직
├── gas/
│   ├── routers/gas_router.py    # POST /api/sensors/info, /api/sensors/gas
│   ├── schemas/gas.py           # GasDataPayload, DeviceInfoPayload
│   └── services/gas_service.py  # DRF 전송 + 공유 상태 갱신
├── power/
│   ├── routers/power_router.py  # POST /api/power/onoff|current|voltage|watt
│   ├── schemas/power.py         # PowerOnOffPayload, PowerCurrentPayload 등
│   └── services/power_service.py# DRF 전송(BackgroundTasks) + 공유 상태 갱신 + build_equipment()
├── positioning/
│   ├── routers/position_router.py # WS /ws/positions/ (더미 위치 브로드캐스트)
│   ├── schemas/position.py
│   └── services/position_service.py # DRF 저장 (지오펜스 근접 시만)
├── websocket/
│   ├── state.py                 # 프로세스 공유 상태 (모든 도메인이 import)
│   ├── routers/ws_router.py     # WS /ws/sensors/, WS /ws/position/
│   └── services/broadcast.py   # build_broadcast_payload() 조립 로직
└── dummies/
    ├── gas_dummy.py             # 가스 더미 전송 스크립트
    └── power_dummy.py           # 전력 더미 전송 스크립트
```

---

## 핵심 변경 내용

### 1. 내부 HTTP Push 제거 — `websocket/state.py` 도입

`websocket_jhh.py`에서 가스 알람을 동일 프로세스에 HTTP POST로 전달하던 구조를 폐기했다.
대신 모든 도메인 모듈이 `websocket/state.py`의 공유 상태를 직접 읽고 쓴다.

```python
# websocket/state.py
worker_positions: dict[int, dict] = {}
active_alarms: list[dict] = []
latest_gas_snapshot: dict = {}
power_latest: dict = {"onoff": {}, "current": {}, "voltage": {}, "watt": {}, "updated_at": None}
```

| 제거된 엔드포인트 | 대체 방법 |
|------------------|-----------|
| `POST /internal/alarm/` | `gas_service.py`가 `active_alarms.extend(alarms)` 직접 호출 |
| `POST /internal/gas-snapshot/` | `gas_service.py`가 `latest_gas_snapshot.update(snapshot)` 직접 호출 |

### 2. 브로드캐스트 페이로드 통합 — `websocket/services/broadcast.py`

CJY의 전력 실데이터 기반 `_build_broadcast_payload()`와 jhh의 알람/가스 스냅샷 추가분을 하나로 합쳤다.

- `power_latest` 기준 stale 판정 (8초 초과 시 빈 equipment 반환)
- `active_alarms` 포함 후 즉시 비움 (다음 틱에 중복 전달 방지)
- `**latest_gas_snapshot` spread — 가스 측정값 + 위험도 포함

### 3. 전력 라우터 — BackgroundTasks 패턴

전력 4종(onoff/current/voltage/watt) 수신 시 공유 상태를 즉시 갱신하고,
DRF 저장은 `BackgroundTasks`로 비동기 처리하여 WebSocket 흐름을 블로킹하지 않는다.

```
POST /api/power/watt
  → update_power_state() (즉시, 동기)
  → post_to_drf()        (BackgroundTask, 비동기)
  → return 201
```

### 4. positioning DRF_BASE_URL 환경변수 처리

```python
# 변경 전
DRF_BASE_URL = "http://127.0.0.1:8000"

# 변경 후
DRF_BASE_URL = os.getenv("DRF_BASE_URL", "http://127.0.0.1:8000")
```

### 5. positioning DRF 저장 로그 개선

DRF 응답 body의 실제 `saved` 값을 출력하도록 수정.
이전에는 HTTP 201 수신 시 무조건 "4명 저장 완료"로 출력되어 0건 저장도 완료처럼 보이는 문제가 있었다.

```
변경 전: [positioning] DRF 저장 완료: 4명
변경 후: [positioning] 전송: 4명, 저장: 0명 (지오펜스 근접 시만 저장)
```

---

## 삭제된 파일 목록

| 파일/폴더 | 이유 |
|-----------|------|
| `websocket.py` | `websocket/routers/ws_router.py` + `websocket/services/broadcast.py`로 대체 |
| `websocket_CJY.py` | 동일 |
| `websocket_jhh.py` | 동일 (내부 HTTP Push 엔드포인트도 함께 제거) |
| `main.py` | `app.py`로 대체 |
| `dummy_sender.py` | `dummies/gas_dummy.py`로 이동 |
| `routers/` | `gas/routers/`로 이동 |
| `schemas/` | `gas/schemas/`로 이동 |
| `power_system/` | `power/`로 이동, `dummies/power_dummy.py`로 분리 |

---

## 등록된 라우트 전체 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/sensors/info` | 가스 센서 기기 정보 수신 |
| POST | `/api/sensors/gas` | 가스 측정값 수신 → DRF 저장 + 공유 상태 갱신 |
| POST | `/api/power/onoff` | 전력 ON/OFF 수신 |
| POST | `/api/power/current` | 전류 수신 |
| POST | `/api/power/voltage` | 전압 수신 |
| POST | `/api/power/watt` | 전력(W) 수신 |
| WS | `/ws/sensors/` | 브라우저용 — 1초마다 통합 페이로드 송출 |
| WS | `/ws/position/` | IoT 디바이스용 — 위치 수신 → DRF 저장 → 공유 상태 갱신 |
| WS | `/ws/positions/` | 브라우저용 — 더미 작업자 위치 1초마다 송출 |
| GET | `/health/` | 헬스 체크 |

---

## 데이터 흐름 요약

```
[가스 센서 장비]
    POST /api/sensors/gas
        → gas_service.process_gas_data()
            → DRF /api/monitoring/gas/ (저장)
            → latest_gas_snapshot.update()   ← state.py
            → active_alarms.extend()         ← state.py

[전력 센서 장비]
    POST /api/power/watt (etc.)
        → power_service.update_power_state() ← state.py (즉시)
        → BackgroundTask: post_to_drf()      → DRF /monitoring/api/power/data/

[IoT 위치 장비]
    WS /ws/position/
        → _forward_to_drf()                  → DRF /positioning/api/receive/ (지오펜스 근접 시만 저장)
        → worker_positions[id] = {...}       ← state.py

[브라우저]
    WS /ws/sensors/
        ← build_broadcast_payload()
            ← power_latest    (state.py)     → equipment[], total_power_kw
            ← latest_gas_snapshot (state.py) → 가스 측정값 + 위험도
            ← active_alarms   (state.py)     → alarms[] (전송 후 비움)
            ← worker_positions (state.py)    → worker_positions{}
```

---

## 서버 실행

```bash
cd fastapi-server
uvicorn app:app --reload --port 8001
```

## 더미 실행

```bash
# 가스 더미 (1초 주기)
python -m dummies.gas_dummy

# 전력 더미 (3초 주기)
python -m dummies.power_dummy
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DRF_BASE_URL` | `http://localhost:8000` | DRF 서버 주소 (기본값으로 로컬 개발 시 생략 가능) |
| `DRF_SERVICE_TOKEN` | `""` | Bearer 토큰 (미설정 시 인증 헤더 생략) |
