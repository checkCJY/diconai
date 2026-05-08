"""
pytest 공통 fixture (Phase 1~4 회귀 테스트용).

[scope 정책]
- 마이그 시드 데이터(Threshold, RiskLevelStandard, HazardType, Menu, RoleProfile)는
  마이그 적용 시점에 자동 시드되어 DB에 존재. 별도 fixture 불필요.
- facility / gas_sensor / worker / power_device 등 도메인 인스턴스는 함수 단위 fixture.
- pytest.mark.django_db는 각 테스트 함수가 명시.
"""

import pytest


@pytest.fixture
def facility(db):
    from apps.facilities.models import Facility

    return Facility.objects.create(
        name="회귀 점검 공장",
        address="테스트시 회귀구 1-2",
    )


@pytest.fixture
def gas_sensor(db, facility):
    from apps.facilities.models import GasSensor

    return GasSensor.objects.create(
        facility=facility,
        device_id="GAS-REGRESS-01",
        device_name="회귀 점검 가스 센서",
        x=10.0,
        y=20.0,
    )


@pytest.fixture
def power_device(db, facility):
    from apps.facilities.models import PowerDevice

    return PowerDevice.objects.create(
        facility=facility,
        device_id="POW-REGRESS-01",
        device_name="회귀 점검 전력 장비",
        x=30.0,
        y=40.0,
    )


@pytest.fixture
def position_node(db, facility):
    from apps.facilities.models import PositionNode

    return PositionNode.objects.create(
        facility=facility,
        device_id="NODE-REGRESS-01",
        device_name="회귀 점검 위치 노드",
        x=50.0,
        y=60.0,
    )


@pytest.fixture
def worker_user(db):
    from apps.accounts.models import CustomUser

    return CustomUser.objects.create_user(
        username="regress_worker",
        password="regress-pass-1!",
        user_type="worker",
        name="회귀 작업자",
    )
