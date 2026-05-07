# fastapi-server/positioning/schemas/position.py
from pydantic import BaseModel, Field
from datetime import datetime


class WorkerPositionSchema(BaseModel):
    """작업자 위치 데이터 스키마 — Pydantic 검증"""

    worker_id: int
    worker_name: str
    facility_id: int
    x: float = Field(..., ge=0)  # 0 이상
    y: float = Field(..., ge=0)  # 0 이상
    movement_status: str = Field(default="moving")
    measured_at: datetime


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
