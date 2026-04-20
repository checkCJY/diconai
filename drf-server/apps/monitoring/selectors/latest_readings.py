# monitoring/selectors/latest_readings.py

from django.db.models import Subquery, OuterRef
from apps.monitoring.models import GasData


def get_latest_gas_data_per_sensor(facility_id: int):
    """
    공장 내 센서별 최신 가스 측정값 조회 (N+1 없이)
    """
    # 센서별 최신 measured_at 서브쿼리
    latest_time = (
        GasData.objects.filter(
            gas_sensor=OuterRef("gas_sensor"),
        )
        .order_by("-measured_at")
        .values("measured_at")[:1]
    )

    return GasData.objects.filter(
        gas_sensor__facility_id=facility_id,
        measured_at=Subquery(latest_time),
    ).select_related("gas_sensor")
