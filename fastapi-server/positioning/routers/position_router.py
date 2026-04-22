# fastapi-server/positioning/routers/position_router.py
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from positioning.services.position_service import (
    update_worker_positions,
    save_positions_to_drf,
)

router = APIRouter()


@router.websocket("/ws/positions/")
async def position_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # 1. 작업자 위치 더미 데이터 생성
            positions = update_worker_positions()

            # 2. 브라우저로 즉시 송출
            await websocket.send_json(
                {
                    "worker_positions": [
                        {**p.model_dump(), "measured_at": p.measured_at.isoformat()}
                        for p in positions
                    ]
                }
            )

            # 3. DRF 저장 비동기 (fire-and-forget)
            asyncio.create_task(save_positions_to_drf(positions))

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        print("[positioning] Client disconnected")
