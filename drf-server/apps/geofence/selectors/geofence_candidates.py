# geofence/selectors/geofence_candidates.py

from apps.geofence.models import GeoFence


def find_geofence_containing_point(
    facility_id: int,
    x: float,
    y: float,
) -> GeoFence | None:
    """
    주어진 좌표가 속한 구역 찾기
    여러 구역 겹치면 risk_level 높은 구역 우선
    """
    candidates = GeoFence.objects.filter(
        facility_id=facility_id,
        is_active=True,
    ).order_by("-risk_level")  # danger > warning > normal

    for fence in candidates:
        if fence.contains_point(x, y):
            return fence
    return None
