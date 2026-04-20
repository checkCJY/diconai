# facilities/selectors/active_devices.py

from facilities.models import GasSensor, PowerDevice


def get_active_devices_for_facility(facility_id: int):
    """공장의 활성 장비 전체 조회 (대시보드용)"""
    gas_sensors = GasSensor.objects.filter(
        facility_id=facility_id,
        is_active=True,
    )
    power_devices = PowerDevice.objects.filter(
        facility_id=facility_id,
        is_active=True,
    )
    return {
        "gas_sensors": list(gas_sensors),
        "power_devices": list(power_devices),
    }
