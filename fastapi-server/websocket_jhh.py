"""
websocket_jhh.py — jhh 작업본 (websocket.py 기반)

[추가된 역할] 가스 알람 실시간 Push (CM-07 / MN-03)
  FastAPI sensors(8001)가 DRF 알람 응답을 받으면
  POST /internal/alarm/ 로 Push → /ws/sensors/ 다음 틱에 브라우저로 전달

  POST /internal/gas-snapshot/ 로 최신 가스 측정값 캐시 → /ws/sensors/ 페이로드에 포함

흐름:
  sensors(8001) → POST /internal/gas-snapshot/  → latest_gas_snapshot 갱신
  sensors(8001) → POST /internal/alarm/          → active_alarms 큐 추가
  브라우저      ← ws/sensors/                   ← 알람 + 가스 스냅샷 포함 페이로드
"""

import asyncio
import os
import random
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from positioning.routers.position_router import router as positioning_router

DRF_BASE_URL = os.getenv("DRF_BASE_URL", "http://localhost:8000")
DRF_SERVICE_TOKEN = os.getenv("DRF_SERVICE_TOKEN", "")
POSITION_ENDPOINT = f"{DRF_BASE_URL}/positioning/api/receive/"

app = FastAPI()
app.include_router(positioning_router)

# 작업자 최신 위치 공유 상태
worker_positions: dict[int, dict] = {}

# 가스 알람 이벤트 큐 — /internal/alarm/ Push 수신, /ws/sensors/ 틱마다 포함 후 비움
active_alarms: list[dict] = []

# 최신 가스 측정 스냅샷 — /internal/gas-snapshot/ Push 수신
latest_gas_snapshot: dict = {}


# ────────────────────────────────────────────────────────────
# 내부 Push 엔드포인트 — FastAPI sensors(8001) 전용
# ────────────────────────────────────────────────────────────

class AlarmPushRequest(BaseModel):
    alarms: list[dict[str, Any]]


class GasSnapshotRequest(BaseModel):
    snapshot: dict[str, Any]


@app.post("/internal/alarm/")
async def receive_alarm(body: AlarmPushRequest):
    active_alarms.extend(body.alarms)
    return {"queued": len(body.alarms)}


@app.post("/internal/gas-snapshot/")
async def receive_gas_snapshot(body: GasSnapshotRequest):
    latest_gas_snapshot.update(body.snapshot)
    return {"ok": True}


# ────────────────────────────────────────────────────────────
# 가스 / 전력 / AI 더미 데이터 생성
# ────────────────────────────────────────────────────────────
EQUIPMENT_LIST = [
    {"name": "압연기", "base_mwh": 15.2, "base_temp": 125},
    {"name": "송풍기", "base_mwh": 15.0, "base_temp": 125},
    {"name": "집진기", "base_mwh": 5.2, "base_temp": 125},
    {"name": "전자기 교반기", "base_mwh": 3.4, "base_temp": 125},
]


def get_power_level(mwh: float, name: str) -> str:
    if name in ("압연기", "송풍기") and mwh > 14:
        return "danger"
    if mwh > 4.5:
        return "caution"
    return "safe"


def get_temp_sensor_data() -> dict:
    is_danger = random.random() < 0.1

    equipment = []
    total_power = 0.0
    for eq in EQUIPMENT_LIST:
        fluctuation = round(random.uniform(-0.5, 0.5), 1)
        mwh = round(eq["base_mwh"] + fluctuation, 1)
        temp = eq["base_temp"] + random.randint(-3, 5)
        level = get_power_level(mwh, eq["name"])
        total_power += mwh
        equipment.append({"name": eq["name"], "mwh": mwh, "temp": temp, "level": level})

    total_power_mw = round(1200 + random.uniform(-50, 100))
    power_change_pct = round((total_power_mw - 1076) / 1076 * 100, 1)

    danger_eq = next((e for e in equipment if e["level"] == "danger"), equipment[0])
    ai_eta_min = random.randint(15, 40)
    ai_max_load_kw = round(danger_eq["mwh"] * 1000 * random.uniform(1.05, 1.2))
    ai_max_load_pct = round(ai_max_load_kw / (danger_eq["mwh"] * 1000) * 100)

    payload = {
        "device_id": "sensor-01",
        "timestamp": datetime.now().isoformat(),
        "co": random.randint(200, 300) if is_danger else random.randint(5, 20),
        "h2s": random.randint(15, 30) if is_danger else random.randint(0, 5),
        "o2": round(random.uniform(18.0, 19.0), 1)
        if is_danger
        else round(random.uniform(20.5, 21.0), 1),
        "level": "위험" if is_danger else "정상",
        "total_power_mw": total_power_mw,
        "power_change_pct": power_change_pct,
        "equipment": equipment,
        "ai_power_equipment": danger_eq["name"],
        "ai_eta_min": ai_eta_min,
        "ai_max_load_kw": ai_max_load_kw,
        "ai_max_load_pct": ai_max_load_pct,
        "worker_positions": dict(worker_positions),
        # 가스 알람 이벤트 — 새 Event 생성 시만 포함, 전송 후 큐 비움
        "alarms": list(active_alarms),
        # 최신 가스 측정값 + 위험도 (sensors 8001이 Push)
        **latest_gas_snapshot,
    }
    active_alarms.clear()
    return payload


# ────────────────────────────────────────────────────────────
# 브라우저용 센서 스트림
# ────────────────────────────────────────────────────────────
@app.websocket("/ws/sensors/")
async def sensor_stream(websocket: WebSocket):
    """브라우저가 연결. 1초마다 통합 페이로드(센서+전력+AI+위치+알람) 송출."""
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(get_temp_sensor_data())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print("[sensors] 브라우저 연결 종료")


# ────────────────────────────────────────────────────────────
# IoT 디바이스용 위치 수신 스트림
# ────────────────────────────────────────────────────────────
async def _forward_to_drf(payload: dict) -> dict:
    """DRF POST /positioning/api/receive/ 호출."""
    headers = {"Content-Type": "application/json"}
    if DRF_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {DRF_SERVICE_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(POSITION_ENDPOINT, json=payload, headers=headers)
            print(
                f"[position] DRF {res.status_code}: worker={payload['worker_id']} ({payload['x']}, {payload['y']})"
            )
            if res.status_code == 201:
                return {"status": "ok", **res.json()}
            return {"status": "error", "message": f"DRF {res.status_code}: {res.text}"}
    except httpx.TimeoutException:
        return {"status": "error", "message": "DRF 응답 타임아웃"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.websocket("/ws/position/")
async def position_stream(websocket: WebSocket):
    """
    IoT 디바이스가 연결. 위치 데이터를 수신하여 DRF에 저장하고
    worker_positions 공유 상태를 갱신 → /ws/sensors/ 다음 틱에 브라우저로 전달.
    """
    await websocket.accept()
    print("[position] IoT 디바이스 연결됨")

    try:
        while True:
            data = await websocket.receive_json()

            required = ["worker_id", "facility_id", "x", "y"]
            missing = [f for f in required if f not in data]
            if missing:
                await websocket.send_json(
                    {"status": "error", "message": f"필수 필드 누락: {missing}"}
                )
                continue

            worker_id = int(data["worker_id"])
            payload = {
                "worker_id": worker_id,
                "facility_id": int(data["facility_id"]),
                "x": float(data["x"]),
                "y": float(data["y"]),
                "measured_at": datetime.now(timezone.utc).isoformat(),
            }

            result = await _forward_to_drf(payload)

            if result["status"] == "ok":
                worker_positions[worker_id] = {
                    "x": payload["x"],
                    "y": payload["y"],
                    "facility_id": payload["facility_id"],
                    "updated_at": payload["measured_at"],
                }

            await websocket.send_json(result)

    except WebSocketDisconnect:
        print("[position] IoT 디바이스 연결 종료")
    except Exception as e:
        print(f"[position] 예외: {e}")
        await websocket.close()
