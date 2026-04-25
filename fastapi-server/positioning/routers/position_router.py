# positioning/routers/position_router.py — 더미 작업자 위치 WebSocket 엔드포인트
#
# 브라우저를 대상으로 더미 작업자 위치를 1초마다 송출하는 WebSocket 라우터.
# 실제 IoT 장비 연동 전까지 DUMMY_WORKERS 시뮬레이션 데이터를 사용한다.
#   WS /ws/positions/ : 브라우저 연결 → 1초마다 작업자 위치 배열 전송 + DRF 저장
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from positioning.services.position_service import (
    update_worker_positions,
    save_positions_to_drf,
)

router = APIRouter()


@router.websocket("/ws/positions/")
async def position_stream(websocket: WebSocket):
    """
    브라우저에 더미 작업자 위치를 1초마다 스트리밍한다.

    매 틱마다 update_worker_positions()로 더미 이동을 계산해 브라우저에 즉시 전송하고,
    save_positions_to_drf()를 비동기 태스크로 실행해 DRF에 저장한다.
    DRF 저장은 지오펜스 근접 시에만 실제 DB 레코드가 생성된다.
    """
    await websocket.accept()
    try:
        while True:
            positions = update_worker_positions()

            await websocket.send_json(
                {
                    "worker_positions": [
                        {**p.model_dump(), "measured_at": p.measured_at.isoformat()}
                        for p in positions
                    ]
                }
            )

            asyncio.create_task(save_positions_to_drf(positions))

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        print("[positioning] Client disconnected")
