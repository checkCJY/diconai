# facilities/services/device_service.py


def retire_gas_sensor(sensor_id: int, actor_user_id: int, reason: str = ""):
    """
    가스 센서 철거 처리 — 물리 삭제가 아닌 Soft Delete
    """
    from apps.facilities.models import GasSensor
    from apps.core.models import SystemLog
    from apps.core.services.audit_service import log_action

    sensor = GasSensor.objects.get(pk=sensor_id)
    sensor.deactivate()

    log_action(
        actor_id=actor_user_id,
        action_type=SystemLog.ActionType.DEVICE_DEACTIVATE,
        target_model="GasSensor",
        target_id=sensor.pk,
        old_value={"is_active": True, "status": "normal"},
        new_value={"is_active": False, "status": "inactive", "reason": reason},
    )
