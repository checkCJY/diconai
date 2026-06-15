"""가스 측정값 미등록 센서 거부 회귀 가드 (P1 신규).

GasDataCreateSerializer.validate 는 device_id 를 활성 GasSensor 로 매핑한다
(gas_data.py L64-74). 미등록/비활성 device_id 는 ValidationError(device_id)로 거부 —
fastapi 단의 404 매핑([[gas-unregistered-404]])이 의존하는 DRF 측 계약.
"""

import pytest
from rest_framework import serializers

from apps.monitoring.serializers.gas_data import GasDataCreateSerializer


@pytest.mark.django_db
def test_unregistered_device_id_rejected():
    """미등록 device_id → ValidationError(device_id 키)."""
    ser = GasDataCreateSerializer()
    with pytest.raises(serializers.ValidationError) as exc:
        ser.validate({"device_id": "NOPE-UNREGISTERED"})
    assert "device_id" in exc.value.detail


@pytest.mark.django_db
def test_registered_active_sensor_resolves_to_fk(gas_sensor):
    """등록된 활성 센서 device_id → gas_sensor FK 로 매핑."""
    ser = GasDataCreateSerializer()
    attrs = ser.validate({"device_id": gas_sensor.device_id})
    assert attrs["gas_sensor"] == gas_sensor
