# positioning/selectors/latest_positions.py

from django.db.models import Subquery, OuterRef
from positioning.models import WorkerPosition


def get_latest_positions_per_worker(facility_id: int):
    """
    공장 내 모든 작업자의 최신 위치 조회 (N+1 없이)
    대시보드 지도 초기 렌더링용
    """
    latest_time = (
        WorkerPosition.objects.filter(
            worker=OuterRef("worker"),
        )
        .order_by("-measured_at")
        .values("measured_at")[:1]
    )

    return WorkerPosition.objects.filter(
        facility_id=facility_id,
        worker__isnull=False,  # 탈퇴 작업자 제외
        measured_at=Subquery(latest_time),
    ).select_related("worker", "current_geofence")
