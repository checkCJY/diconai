"""
전력 시스템 WebSocket 통합 테스트 서버.

목적: DRF 없이 더미 센더 → FastAPI → WebSocket → 브라우저 흐름 단독 검증
      3순위(websocket.py 통합) 전에 페이로드 구조와 화면 렌더링을 미리 확인

실행:
    cd fastapi-server
    uvicorn power_system.websocket_test:app --reload --port 8002

테스트 흐름:
    1. 이 서버 실행 (port 8002)
    2. 더미 전송 스크립트 실행:
       python -c "
       from power_system.power_dummy_sender import *
       import time
       while True:
           send_data('http://localhost:8002/api/power/onoff',   generate_power_onoff_data(),   'ONOFF')
           send_data('http://localhost:8002/api/power/current', generate_power_current_data(), 'CURRENT')
           send_data('http://localhost:8002/api/power/voltage', generate_power_voltage_data(), 'VOLTAGE')
           send_data('http://localhost:8002/api/power/watt',    generate_power_watt_data(),    'WATT')
           time.sleep(3)
       "
    3. 브라우저에서 ws://localhost:8002/ws/power/ 연결 확인
       또는 아래 콘솔 스니펫 사용:
       const ws = new WebSocket('ws://localhost:8002/ws/power/');
       ws.onmessage = e => console.log(JSON.parse(e.data));
"""

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from power_system.schemas import (
    PowerCurrentPayload,
    PowerOnOffPayload,
    PowerVoltagePayload,
    PowerWattPayload,
)

app = FastAPI(title="전력 WebSocket 테스트 서버")

# ──────────────────────────────────────────────────────────────
# 공유 상태 — power_latest
# router 수신 시 갱신, /ws/power/ 송출 시 스냅샷으로 포함
# ──────────────────────────────────────────────────────────────
power_latest: dict = {
    "onoff": {},  # {"1": bool, ..., "16": bool}
    "current": {},  # {1: float, ..., 16: float}
    "voltage": {},  # {1: float, ..., 16: float}
    "watt": {},  # {1: float, ..., 16: float}
    "updated_at": None,  # 마지막 갱신 시각 (UTC ISO)
}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────
# 수신 엔드포인트 — DRF 전송 없이 power_latest만 갱신
# ──────────────────────────────────────────────────────────────


@app.post("/api/power/onoff", status_code=201)
async def recv_onoff(payload: PowerOnOffPayload):
    power_latest["onoff"] = payload.to_snapshot()
    power_latest["updated_at"] = _now_utc_iso()
    return {"status": "ok", "updated": "onoff"}


@app.post("/api/power/current", status_code=201)
async def recv_current(payload: PowerCurrentPayload):
    power_latest["current"] = payload.to_channel_values()
    power_latest["updated_at"] = _now_utc_iso()
    return {"status": "ok", "updated": "current"}


@app.post("/api/power/voltage", status_code=201)
async def recv_voltage(payload: PowerVoltagePayload):
    power_latest["voltage"] = payload.to_channel_values()
    power_latest["updated_at"] = _now_utc_iso()
    return {"status": "ok", "updated": "voltage"}


@app.post("/api/power/watt", status_code=201)
async def recv_watt(payload: PowerWattPayload):
    power_latest["watt"] = payload.to_channel_values()
    power_latest["updated_at"] = _now_utc_iso()
    return {"status": "ok", "updated": "watt"}


# ──────────────────────────────────────────────────────────────
# WebSocket — 브라우저로 1초마다 power_latest 송출
# ──────────────────────────────────────────────────────────────


@app.websocket("/ws/power/")
async def power_stream(websocket: WebSocket):
    """
    브라우저가 연결하면 1초마다 power_latest 스냅샷을 JSON으로 송출.

    페이로드 구조:
    {
        "updated_at": "2026-04-22T10:00:00+00:00" | null,
        "onoff":   {"1": true, "2": false, ..., "16": true},
        "current": {1: 12.5, 2: -1.0, ..., 16: 8.3},
        "voltage": {1: 220.0, ...},
        "watt":    {1: 2750.0, ...}
    }
    updated_at == null 이면 아직 데이터 미수신 상태
    """
    await websocket.accept()
    print("[ws/power] 브라우저 연결됨")
    try:
        while True:
            await websocket.send_json(dict(power_latest))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print("[ws/power] 브라우저 연결 종료")


"""
터미널 A — 테스트 서버 실행

cd fastapi-server
uvicorn power_system.websocket_test:app --reload --port 8002

터미널 B — 더미 전송

cd fastapi-server
python -c "
from power_system.power_dummy_sender import *
import time
while True:
    send_data('http://localhost:8002/api/power/onoff',   generate_power_onoff_data(),   'ONOFF')
    send_data('http://localhost:8002/api/power/current', generate_power_current_data(), 'CURRENT')
    send_data('http://localhost:8002/api/power/voltage', generate_power_voltage_data(), 'VOLTAGE')
    send_data('http://localhost:8002/api/power/watt',    generate_power_watt_data(),    'WATT')
    time.sleep(3)
"

브라우저 콘솔 — WebSocket 수신 확인

const ws = new WebSocket('ws://localhost:8002/ws/power/');
ws.onmessage = e => console.log(JSON.parse(e.data));
"""
