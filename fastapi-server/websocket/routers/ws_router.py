# websocket/routers/ws_router.py — WebSocket 엔드포인트
import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config import settings
from websocket.services.broadcast import build_broadcast_payload
from websocket.state import worker_positions

POSITION_ENDPOINT = f"{settings.DRF_BASE_URL}/api/positioning/receive/"

router = APIRouter()


async def _forward_to_drf(payload: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if settings.DRF_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {settings.DRF_SERVICE_TOKEN}"
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


@router.websocket("/ws/sensors/")
async def sensor_stream(websocket: WebSocket):
    await websocket.accept()
    print("[ws/sensors] 브라우저 연결됨")
    try:
        while True:
            await websocket.send_json(build_broadcast_payload())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print("[ws/sensors] 브라우저 연결 종료")


@router.websocket("/ws/position/")
async def position_stream(websocket: WebSocket):
    await websocket.accept()
    print("[ws/position] IoT 디바이스 연결됨")
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
        print("[ws/position] IoT 디바이스 연결 종료")
    except Exception as e:
        print(f"[ws/position] 예외: {e}")
        await websocket.close()
