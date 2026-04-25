# websocket/routers/ws_router.py — 브라우저/IoT WebSocket 엔드포인트
#
# 두 가지 WebSocket 연결을 처리한다.
#   WS /ws/sensors/  : 브라우저 연결. 1초마다 통합 페이로드(가스+전력+알람+작업자 위치)를 송출한다.
#   WS /ws/position/ : IoT 위치 장비 연결. 위치 데이터를 수신해 DRF에 저장하고
#                      worker_positions 공유 상태를 갱신한다.
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
    """
    IoT 장비로부터 수신한 위치 데이터를 DRF에 저장한다.

    성공 시 {"status": "ok", ...DRF 응답} 을 반환하고,
    타임아웃·예외 발생 시 {"status": "error", "message": ...} 를 반환한다.
    """
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
    """
    브라우저용 실시간 통합 데이터 스트림.

    1초마다 build_broadcast_payload()로 조립한 페이로드를 전송한다.
    페이로드에는 가스 측정값·위험도, 전력 설비 현황, 알람 목록, 작업자 위치가 포함된다.
    """
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
    """
    IoT 위치 장비용 수신 스트림.

    장비로부터 worker_id, facility_id, x, y 를 수신해 DRF에 저장하고
    worker_positions 공유 상태를 갱신한다.
    갱신된 위치는 /ws/sensors/ 다음 틱에 브라우저로 전달된다.
    필수 필드가 누락된 경우 에러 응답을 반환하고 다음 수신을 계속 대기한다.
    """
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
