"""
WorkerPositionSchema 검증 스모크 테스트 (PR-F).

[회귀 커버]
- node_id Optional 필드 (Phase 3-a) — 펌웨어 갱신 전 None 허용
- x/y >= 0 검증
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from positioning.schemas.position import WorkerPositionSchema


def test_node_id_optional_default_none():
    """node_id 미제공 시 None — 펌웨어 갱신 전 호환."""
    schema = WorkerPositionSchema(
        worker_id=1,
        worker_name="작업자A",
        facility_id=1,
        x=10.0,
        y=20.0,
        measured_at=datetime.now(),
    )
    assert schema.node_id is None


def test_node_id_string_accepted():
    """node_id로 PositionNode.device_id 문자열 그대로 전달."""
    schema = WorkerPositionSchema(
        worker_id=1,
        worker_name="작업자A",
        facility_id=1,
        x=10.0,
        y=20.0,
        measured_at=datetime.now(),
        node_id="NODE-001",
    )
    assert schema.node_id == "NODE-001"


def test_negative_coordinates_rejected():
    """x/y < 0 → ValidationError."""
    with pytest.raises(ValidationError):
        WorkerPositionSchema(
            worker_id=1,
            worker_name="A",
            facility_id=1,
            x=-1.0,
            y=20.0,
            measured_at=datetime.now(),
        )


def test_movement_status_default_moving():
    """movement_status 기본값 'moving'."""
    schema = WorkerPositionSchema(
        worker_id=1,
        worker_name="A",
        facility_id=1,
        x=10.0,
        y=20.0,
        measured_at=datetime.now(),
    )
    assert schema.movement_status == "moving"
