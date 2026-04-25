# apps/geofence/services/geofence_service.py

from django.db import transaction
from apps.geofence.models import GeoFence  # ← 경로 수정


@transaction.atomic
def create_geofence(
    facility_id: int,
    name: str,
    polygon: list,
    risk_level: str,
    description: str = "",
):
    """
    지오펜스 신규 생성
    - validate_polygon은 모델 clean()에서 자동 호출
    - 관리자 UI에서 그리기 완료 후 저장 시점
    """
    geofence = GeoFence(
        facility_id=facility_id,
        name=name,
        polygon=polygon,
        risk_level=risk_level,
        description=description,
    )
    geofence.full_clean()
    geofence.save()
    return geofence


@transaction.atomic
def update_polygon(
    geofence_id: int,
    new_polygon: list,
    actor_user_id: int,
):
    """
    polygon 수정 시 positioning 앱에 재계산 트리거
    (3차: positioning, audit 미구현으로 주석 처리)
    """
    geofence = GeoFence.objects.select_for_update().get(pk=geofence_id)
    geofence.polygon = new_polygon
    geofence.full_clean()
    geofence.save(update_fields=["polygon", "updated_at"])

    # TODO: 4차에서 구현
    # from apps.positioning.services.position_service import (
    #     recalculate_worker_positions_for_facility,
    # )
    # recalculate_worker_positions_for_facility(geofence.facility_id)

    # positioning 앱에 캐시 재계산 요청
    from apps.positioning.services.position_service import (
        recalculate_worker_positions_for_facility,
    )

    recalculate_worker_positions_for_facility(geofence.facility_id)

    # 감사 로그
    from apps.core.services.audit_service import log_action
    from apps.core.models import SystemLog

    log_action(
        actor_id=actor_user_id,
        action_type=SystemLog.ActionType.GEOFENCE_UPDATE,
        target_model="GeoFence",
        target_id=geofence.pk,
        new_value={"polygon": new_polygon},
        description=f"지오펜스 '{geofence.name}' polygon 수정",
    )
