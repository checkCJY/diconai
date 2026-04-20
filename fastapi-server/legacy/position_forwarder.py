"""
position_forwarder.py — 작업자 위치 데이터 수신 및 DRF 전달

IoT 디바이스(웨어러블 등)에서 WebSocket으로 위치를 전송하면,
이 서버가 받아서 DRF POST /positioning/api/receive/ 로 포워딩한다.

엔드포인트:
  WebSocket ws://fastapi-server/ws/position/
  요청 JSON: { "worker_id": int, "facility_id": int, "x": float, "y": float }
  응답 JSON: { "status": "ok" | "error", "message": str }
"""

import os
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

DRF_BASE_URL = os.getenv("DRF_BASE_URL", "http://localhost:8000")
DRF_SERVICE_TOKEN = os.getenv(
    "DRF_SERVICE_TOKEN",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzc2Njk4NTk4LCJpYXQiOjE3NzY2Njk3OTgsImp0aSI6ImFkYjM5NTBiMTA5MTQxNzJiM2NjNWNmMWI4MjIxNWQxIiwidXNlcl9pZCI6IjIifQ.esbTemoudSOGI-2C8GSzPguoOw8M_7As-DJj2_nites",
)
POSITION_ENDPOINT = f"{DRF_BASE_URL}/positioning/api/receive/"


async def forward_to_drf(payload: dict) -> dict:
    """
    DRF POST /positioning/api/receive/ 호출.
    성공: {"status": "ok", "position_id": int}
    실패: {"status": "error", "message": str}
    """
    headers = {"Content-Type": "application/json"}
    if DRF_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {DRF_SERVICE_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(POSITION_ENDPOINT, json=payload, headers=headers)
            print(
                f"[forwarder] DRF 응답 {res.status_code}: worker={payload['worker_id']} x={payload['x']} y={payload['y']}"
            )
            if res.status_code == 201:
                return {"status": "ok", **res.json()}
            return {"status": "error", "message": f"DRF {res.status_code}: {res.text}"}
    except httpx.TimeoutException:
        print(f"[forwarder] DRF 응답 타임아웃: worker={payload['worker_id']}")
        return {"status": "error", "message": "DRF 응답 타임아웃"}
    except Exception as e:
        print(f"[forwarder] DRF 전송 실패: {e}")
        return {"status": "error", "message": str(e)}


@app.websocket("/ws/position/")
async def position_stream(websocket: WebSocket):
    """
    IoT 디바이스 → FastAPI → DRF 위치 포워딩 WebSocket

    디바이스가 보내는 JSON:
    {
        "worker_id": 1,
        "facility_id": 1,
        "x": 342.5,
        "y": 218.0
    }

    measured_at은 수신 시각(UTC)으로 자동 설정.
    """
    await websocket.accept()
    print("[forwarder] 디바이스 연결됨")

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

            payload = {
                "worker_id": int(data["worker_id"]),
                "facility_id": int(data["facility_id"]),
                "x": float(data["x"]),
                "y": float(data["y"]),
                "measured_at": datetime.now(timezone.utc).isoformat(),
            }

            result = await forward_to_drf(payload)
            await websocket.send_json(result)

    except WebSocketDisconnect:
        print("[forwarder] 디바이스 연결 종료")
    except Exception as e:
        print(f"[forwarder] 예외 발생: {e}")
        await websocket.close()
