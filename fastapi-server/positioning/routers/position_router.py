# positioning/routers/position_router.py — 작업자 위치 수신 및 WebSocket 스트리밍
#
#   POST /api/positioning/receive : 더미 또는 IoT 장비에서 위치 배열을 수신해 공유 상태 갱신
#   WS   /ws/positions/           : 브라우저 연결 → 1초마다 공유 상태의 위치 배열을 전송
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from positioning.schemas.position import WorkerPositionSchema
from positioning.services.position_service import save_positions_to_drf
from websocket import state as ws_state

router = APIRouter()


@router.post("/api/positioning/receive")
async def receive_positions(positions: list[WorkerPositionSchema]):
    """
    더미 스크립트 또는 IoT 장비로부터 작업자 위치 배열을 수신한다.

    공유 상태(worker_positions)를 갱신해 /ws/positions/ 및 /ws/sensors/ 다음 틱에
    브라우저로 전달되도록 하고, DRF에 비동기로 저장을 요청한다.
    """
    now = datetime.now(timezone.utc)
    for p in positions:
        ws_state.worker_positions[p.worker_id] = {
            "x": p.x,
            "y": p.y,
            "facility_id": p.facility_id,
            "worker_name": p.worker_name,
            "movement_status": p.movement_status,
            "updated_at": (p.measured_at or now).isoformat(),
        }
    asyncio.create_task(save_positions_to_drf(positions))
    return {"received": True, "count": len(positions)}


@router.websocket("/ws/positions/")
async def position_stream(websocket: WebSocket):
    """
    브라우저에 작업자 위치를 1초마다 스트리밍한다.

    공유 상태(worker_positions)를 읽어 전송하므로,
    position_dummy.py가 실행 중일 때는 시뮬레이션 데이터가,
    실제 IoT 장비 연결 시에는 실측 데이터가 전달된다.
    """
    await websocket.accept()
    try:
        while True:
            positions = [
                {"worker_id": wid, **data}
                for wid, data in ws_state.worker_positions.items()
            ]
            await websocket.send_json({"worker_positions": positions})
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print("[positioning] Client disconnected")
