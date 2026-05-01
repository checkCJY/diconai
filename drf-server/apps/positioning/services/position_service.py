# positioning/services/position_service.py
import math
from django.db import transaction
from apps.positioning.models import WorkerPosition
from django.utils import timezone
from datetime import timedelta

_RISK_ORDER = {"warning": 1, "danger": 2}


def _get_dangerous_sensors_in_geofence(geofence) -> dict | None:
    """
    지오펜스 polygon 안에 위치한 GasSensor/PowerDevice 중
    현재 warning/danger 상태인 것이 있으면 가장 높은 위험도 정보를 반환한다.
    없으면 None.
    """
    from apps.facilities.models import GasSensor, PowerDevice
    from apps.monitoring.models import GasData, PowerData

    best = None

    for sensor in GasSensor.objects.filter(facility=geofence.facility, is_active=True):
        if not geofence.contains_point(sensor.x, sensor.y):
            continue
        latest = (
            GasData.objects.filter(gas_sensor=sensor)
            .order_by("-measured_at")
            .only("max_risk_level")
            .first()
        )
        if not latest or latest.max_risk_level == "normal":
            continue
        if (
            best is None
            or _RISK_ORDER[latest.max_risk_level] > _RISK_ORDER[best["risk_level"]]
        ):
            best = {
                "risk_level": latest.max_risk_level,
                "source_label": sensor.device_name,
            }

    for device in PowerDevice.objects.filter(
        facility=geofence.facility, is_active=True
    ):
        if not geofence.contains_point(device.x, device.y):
            continue
        latest = (
            PowerData.objects.filter(power_device=device)
            .order_by("-measured_at")
            .only("risk_level")
            .first()
        )
        if not latest or latest.risk_level == "normal":
            continue
        if (
            best is None
            or _RISK_ORDER[latest.risk_level] > _RISK_ORDER[best["risk_level"]]
        ):
            best = {"risk_level": latest.risk_level, "source_label": device.device_name}

    return best


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

    if pos.current_geofence:
        danger_info = _get_dangerous_sensors_in_geofence(pos.current_geofence)
        if danger_info:
            from apps.alerts.tasks import fire_geofence_alarm_task

            fire_geofence_alarm_task.delay(
                worker_id=worker_id,
                facility_id=facility_id,
                geofence_id=pos.current_geofence.id,
                geofence_name=pos.current_geofence.name,
                risk_level=danger_info["risk_level"],
                sensor_source_label=danger_info["source_label"],
            )

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
