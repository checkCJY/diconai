# positioning/routers/position_router.py — 작업자 위치 수신 및 WebSocket 스트리밍
#
#   POST /api/positioning/receive : 더미 또는 IoT 장비에서 위치 배열을 수신해 공유 상태 갱신
#   WS   /ws/positions/           : 브라우저 연결 → 1초마다 공유 상태의 위치 배열을 전송
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from positioning.schemas.position import (
    PositionReceiveResponse,
    WorkerPositionSchema,
)
from positioning.services.position_service import save_positions_to_drf
from websocket import state as ws_state

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/api/positioning/receive",
    response_model=PositionReceiveResponse,
    tags=["positioning"],
    summary="작업자 위치 배열 수신",
    description=(
        "더미 스크립트 또는 IoT 장비로부터 작업자 위치 배열을 수신한다.\n\n"
        "**처리 흐름**:\n"
        "1. 공유 상태(`worker_positions`) 갱신\n"
        "2. `/ws/positions/`(1초 주기) 및 `/ws/sensors/`(broadcast tick)에서 브라우저로 송신\n"
        "3. DRF로 비동기 영속화 (`POST /api/positioning/receive/`)\n"
        "4. 지오펜스 진입 판정은 브라우저 측에서 좌표 비교로 수행"
    ),
    responses={
        422: {"description": "페이로드 검증 실패 (예: x/y 음수)"},
    },
)
async def receive_positions(positions: list[WorkerPositionSchema]):
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
    """브라우저용 작업자 위치 실시간 스트림 (1초 주기).

    페이로드: `{worker_positions: [{worker_id, x, y, facility_id, worker_name, movement_status, updated_at}]}`

    공유 상태(`ws_state.worker_positions`)를 읽어 전송하므로 더미/IoT 데이터 모두 동일 스트림에 노출.
    OpenAPI는 WebSocket을 직접 표현하지 않음 — 자세한 페이로드는 docs/api_specification.md 참조.
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
        logger.info("[ws/positions] action=disconnect")
