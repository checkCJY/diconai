# positioning/services/position_service.py

from django.db import transaction
from apps.positioning.models import WorkerPosition
from django.utils import timezone
from datetime import timedelta


@transaction.atomic
def handle_position_receive(
    worker_id: int,
    facility_id: int,
    x: float,
    y: float,
    measured_at,
):
    """
    FastAPI로부터 위치 데이터 수신 → 저장 → 구역 판정 → 알람 연계
    """
    # 1. 위치 기록 저장
    pos = WorkerPosition.objects.create(
        worker_id=worker_id,
        facility_id=facility_id,
        x=x,
        y=y,
        measured_at=measured_at,
    )

    # 2. 구역 캐시 갱신
    pos.update_geofence_cache()
    pos.save(update_fields=["current_geofence"])

    # 3. 위험구역 진입 감지 시 알람 생성
    if pos.current_geofence and pos.current_geofence.risk_level in (
        "warning",
        "danger",
    ):
        from apps.alerts.services.event_service import create_alarm_and_event
        from apps.core.constants import AlarmType

        create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.GEOFENCE_INTRUSION,
            geofence_id=pos.current_geofence_id,
            worker_id=worker_id,
            risk_level=pos.current_geofence.risk_level,
            source_label=pos.current_geofence.name,
            summary=f"{pos.worker.username}님이 위험구역 '{pos.current_geofence.name}' 진입",
            detected_at=measured_at,
        )

    return pos


def recalculate_worker_positions_for_facility(facility_id: int):
    """
    GeoFence.polygon 변경 후 해당 공장의 최근 위치 전체 재계산
    geofence.services.geofence_service.update_polygon()에서 호출됨

    대용량 고려: 최근 N시간 이내 위치만 재계산
    과거 이력은 그대로 두어도 문제 없음 (과거 폴리곤 기준 판정값)
    """
    since = timezone.now() - timedelta(hours=24)

    positions = WorkerPosition.objects.filter(
        facility_id=facility_id,
        measured_at__gte=since,
    )
    for pos in positions.iterator():
        pos.update_geofence_cache()
        pos.save(update_fields=["current_geofence"])
