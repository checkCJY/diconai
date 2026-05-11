# fastapi-server/positioning/schemas/position.py
from pydantic import BaseModel, Field
from datetime import datetime


class WorkerPositionSchema(BaseModel):
    """작업자 위치 데이터 스키마 — Pydantic 검증

    [node_id — Phase 3-a]
    PositionNode.device_id 그대로 (예: "NODE-001"). 펌웨어 페이로드 갱신 전에는 None.
    """

    worker_id: int
    worker_name: str
    facility_id: int
    x: float = Field(..., ge=0)  # 0 이상
    y: float = Field(..., ge=0)  # 0 이상
    movement_status: str = Field(default="moving")
    measured_at: datetime
    node_id: str | None = None


class WorkerPositionPayload(BaseModel):
    """WebSocket 페이로드에 포함될 작업자 위치 목록"""

    worker_positions: list[WorkerPositionSchema]


# ============================================================
# 응답 스키마 (OpenAPI 자동 문서화용)
# ============================================================


class PositionReceiveResponse(BaseModel):
    """작업자 위치 배열 수신 확인 응답."""

    received: bool
    count: int
