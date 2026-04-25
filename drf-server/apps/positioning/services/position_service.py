# positioning/services/position_service.py
import math
from django.db import transaction
from apps.positioning.models import WorkerPosition
from django.utils import timezone
from datetime import timedelta

# 지오펜스 경계 근접 감지 거리 (픽셀)
PROXIMITY_THRESHOLD = 30


def _distance_point_to_segment(px, py, ax, ay, bx, by) -> float:
    """점 (px, py)에서 선분 (ax,ay)-(bx,by)까지의 최단 거리"""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _distance_to_geofence(x: float, y: float, polygon: list) -> float:
    """작업자 좌표에서 지오펜스 polygon 경계까지의 최단 거리"""
    min_dist = float("inf")
    n = len(polygon)
    for i in range(n):
        ax, ay = polygon[i]
        bx, by = polygon[(i + 1) % n]
        dist = _distance_point_to_segment(x, y, ax, ay, bx, by)
        min_dist = min(min_dist, dist)
    return min_dist


def _is_near_any_geofence(facility_id: int, x: float, y: float) -> bool:
    """
    작업자 좌표가 어느 지오펜스 경계에서 30픽셀 이내인지 확인
    지오펜스 내부에 있는 경우도 포함
    """
    from apps.geofence.models import GeoFence

    geofences = GeoFence.objects.filter(facility_id=facility_id, is_active=True)

    for fence in geofences:
        # 지오펜스 내부에 있는 경우
        if fence.contains_point(x, y):
            return True
        # 지오펜스 경계에서 30픽셀 이내인 경우
        dist = _distance_to_geofence(x, y, fence.polygon)
        if dist <= PROXIMITY_THRESHOLD:
            return True
    return False


@transaction.atomic
def handle_position_receive(
    worker_id: int,
    facility_id: int,
    x: float,
    y: float,
    movement_status: str,
    measured_at,
):
    """
    FastAPI로부터 위치 데이터 수신
    → 지오펜스 30픽셀 이내 접근 시에만 DB 저장
    → 그 외는 저장 안 함 (WebSocket 표시만)
    """
    # 지오펜스 근접 여부 확인
    if not _is_near_any_geofence(facility_id, x, y):
        return None  # 저장 안 함

    # 근접 시에만 저장
    pos = WorkerPosition.objects.create(
        worker_id=worker_id,
        facility_id=facility_id,
        x=x,
        y=y,
        movement_status=movement_status,
        measured_at=measured_at,
    )

    # 구역 캐시 갱신
    pos.update_geofence_cache()
    pos.save(update_fields=["current_geofence"])

    # TODO: 알람 연계는 alerts 팀원 담당
    # if pos.current_geofence and pos.current_geofence.risk_level in ("warning", "danger"):
    #     from apps.alerts.services.event_service import create_alarm_and_event
    #     ...

    return pos


def recalculate_worker_positions_for_facility(facility_id: int):
    """
    GeoFence.polygon 변경 후 해당 공장의 최근 위치 전체 재계산
    """
    since = timezone.now() - timedelta(hours=24)
    positions = WorkerPosition.objects.filter(
        facility_id=facility_id,
        measured_at__gte=since,
    )
    for pos in positions.iterator():
        pos.update_geofence_cache()
        pos.save(update_fields=["current_geofence"])
