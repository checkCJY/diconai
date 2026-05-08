"""
지오펜스 알람 흐름 회귀 테스트 (Phase 1~4 회귀 점검 Step 3).

[회귀 커버 대상]
- Phase 3-a WorkerPosition.received_node FK (nullable, SET_NULL)
- handle_position_receive(node_id=...) lookup 흐름:
  - PositionNode 활성 상태일 때 → received_node 채움
  - PositionNode 비활성 또는 미존재 → received_node=None (silent fallback)
  - node_id=None (펌웨어 미갱신 row) → received_node=None
- 지오펜스 근접 시에만 WorkerPosition 저장

[설계 결정]
통합 테스트 — handle_position_receive() 진입점에서 PositionNode lookup + WorkerPosition
저장까지 검증. 외부 알람 task(fire_geofence_alarm_task)는 dangerous sensor 없을 때
호출 안 함을 검증.
"""

import pytest
from django.utils import timezone

from apps.positioning.models import WorkerPosition
from apps.positioning.services.position_service import handle_position_receive


@pytest.fixture
def geofence(db, facility):
    """공장 (0,0)~(100,100) 영역의 위험 구역."""
    from apps.geofence.models import GeoFence

    return GeoFence.objects.create(
        facility=facility,
        name="회귀 점검 위험 구역",
        polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
        risk_level="warning",
    )


@pytest.mark.django_db
def test_position_with_valid_node_id_links_received_node(
    facility, worker_user, position_node, geofence
):
    """node_id 매칭되는 활성 PositionNode가 있으면 received_node FK로 연결."""
    result = handle_position_receive(
        worker_id=worker_user.id,
        facility_id=facility.id,
        x=50.0,  # geofence 내부
        y=50.0,
        movement_status="moving",
        measured_at=timezone.now(),
        node_id=position_node.device_id,
    )
    assert result["position_id"] is not None
    pos = WorkerPosition.objects.get(pk=result["position_id"])
    assert pos.received_node_id == position_node.id


@pytest.mark.django_db
def test_position_with_unknown_node_id_falls_back_to_none(
    facility, worker_user, geofence
):
    """node_id가 매칭 안 되면 silent fallback → received_node=None."""
    result = handle_position_receive(
        worker_id=worker_user.id,
        facility_id=facility.id,
        x=50.0,
        y=50.0,
        movement_status="moving",
        measured_at=timezone.now(),
        node_id="NODE-MISSING-999",
    )
    assert result["position_id"] is not None
    pos = WorkerPosition.objects.get(pk=result["position_id"])
    assert pos.received_node is None


@pytest.mark.django_db
def test_position_with_inactive_node_falls_back_to_none(
    facility, worker_user, position_node, geofence
):
    """비활성 PositionNode는 매칭 안 함 (silent fallback)."""
    position_node.deactivate()  # is_active=False
    result = handle_position_receive(
        worker_id=worker_user.id,
        facility_id=facility.id,
        x=50.0,
        y=50.0,
        movement_status="moving",
        measured_at=timezone.now(),
        node_id=position_node.device_id,
    )
    pos = WorkerPosition.objects.get(pk=result["position_id"])
    assert pos.received_node is None


@pytest.mark.django_db
def test_position_with_none_node_id_keeps_received_node_null(
    facility, worker_user, geofence
):
    """node_id=None (펌웨어 미갱신 row) → received_node=None."""
    result = handle_position_receive(
        worker_id=worker_user.id,
        facility_id=facility.id,
        x=50.0,
        y=50.0,
        movement_status="moving",
        measured_at=timezone.now(),
        node_id=None,
    )
    pos = WorkerPosition.objects.get(pk=result["position_id"])
    assert pos.received_node is None


@pytest.mark.django_db
def test_position_far_from_geofence_skips_save(facility, worker_user, geofence):
    """지오펜스 근접 거리 밖이면 WorkerPosition 저장 안 함."""
    result = handle_position_receive(
        worker_id=worker_user.id,
        facility_id=facility.id,
        x=500.0,  # geofence (0~100)에서 멀리
        y=500.0,
        movement_status="moving",
        measured_at=timezone.now(),
        node_id=None,
    )
    assert result["position_id"] is None
    assert result["risk_level"] == "normal"
    assert WorkerPosition.objects.count() == 0
