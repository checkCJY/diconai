"""T4 D3 — STATIC_THRESHOLD_AT_FASTAPI neutralize 분기 + shadow_audit 검증.

[검증 대상]
- 기본값 False — 레거시 경로 그대로 (회귀 0)
- True 토글 — 정적 fire skip + STATIC_FIRE_SUPPRESSED_BY_FASTAPI_TOTAL +1
- _shadow_audit — would_fire NORMAL 시 비교 skip
- _shadow_audit — 최근 AlarmRecord 있음 → mismatch 0
- _shadow_audit — 최근 AlarmRecord 없음 → mismatch +1

[설계]
device fixture 는 MagicMock — PowerDevice 필수 필드 (device_code/x/y 등) 가 본
테스트의 분기 검증과 무관. evaluate_power_risk 도 patch 로 강제 결과 — neutralize
분기 자체만 격리 검증.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.core.constants import RiskLevel
from apps.monitoring.services.power_alarm import _shadow_audit, trigger_power_alarms


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def facility(db):
    from apps.facilities.models import Facility

    return Facility.objects.create(name="T4 Test Facility")


@pytest.fixture
def mock_device():
    """power_alarm 이 참조하는 속성만 갖춘 stub — 실 PowerDevice 미사용."""
    device = MagicMock()
    device.id = 9999  # PK
    device.device_id = "t4_test_dev_1"  # AI mute 키 식별자
    device.facility_id = 1
    device.get_channel_label.return_value = "송풍기A"
    return device


def _make_power_data(channel: int, value: float, data_type: str = "watt"):
    """trigger_power_alarms 가 받는 PowerData 의사 객체."""

    class _PD:
        pass

    pd = _PD()
    pd.channel = channel
    pd.value = value
    pd.data_type = data_type
    return pd


@pytest.mark.django_db
@override_settings(STATIC_THRESHOLD_AT_FASTAPI=False, DANGER_CONFIRM_TICKS=1)
def test_neutralize_disabled_keeps_legacy_path(mock_device):
    """기본값 False — 레거시 경로. fire_power_*_task 호출 확인 (회귀 0).

    DANGER_CONFIRM_TICKS=1 로 고정 — 2틱 confirm(#110)과 무관하게 neutralize 분기만
    격리 검증. 1틱이면 첫 틱 즉시 발화(power_alarm.py 의 기존 동작 보장 분기).
    """
    obj = _make_power_data(channel=1, value=10000.0)

    with (
        patch(
            "apps.monitoring.services.power_alarm.evaluate_power_risk",
            return_value=RiskLevel.DANGER,
        ),
        patch(
            "apps.monitoring.services.power_alarm.is_ai_mute_active",
            return_value=False,
        ),
        patch(
            "apps.monitoring.services.power_alarm.fire_power_danger_task"
        ) as mock_fire,
    ):
        trigger_power_alarms([obj], mock_device)

    assert mock_fire.delay.called, "비활성화 모드에서는 정적 fire 가 그대로 작동해야 함"


@pytest.mark.django_db
@override_settings(STATIC_THRESHOLD_AT_FASTAPI=True)
def test_neutralize_enabled_skips_static_fire(mock_device):
    """활성화 모드 — 정적 fire skip + suppressed counter inc."""
    from apps.core.metrics import STATIC_FIRE_SUPPRESSED_BY_FASTAPI_TOTAL

    obj = _make_power_data(channel=1, value=10000.0)

    counter = STATIC_FIRE_SUPPRESSED_BY_FASTAPI_TOTAL.labels(
        device_id=str(mock_device.id), channel="1", level=RiskLevel.DANGER
    )
    before = counter._value.get()

    with (
        patch(
            "apps.monitoring.services.power_alarm.evaluate_power_risk",
            return_value=RiskLevel.DANGER,
        ),
        patch(
            "apps.monitoring.services.power_alarm.fire_power_danger_task"
        ) as mock_fire,
        patch("apps.monitoring.services.power_alarm._shadow_audit") as mock_audit,
    ):
        trigger_power_alarms([obj], mock_device)

    assert not mock_fire.delay.called, "활성화 모드에서는 정적 fire skip"
    assert mock_audit.called, "shadow_audit 가 호출되어야 함"
    assert counter._value.get() == before + 1


@pytest.mark.django_db
def test_shadow_audit_skips_when_would_fire_normal(mock_device):
    """정적 평가 NORMAL — 비교 자체 skip (counter inc 0)."""
    from apps.core.metrics import STATIC_AUDIT_MISMATCH_TOTAL

    counter = STATIC_AUDIT_MISMATCH_TOTAL.labels(
        device_id=str(mock_device.id), channel="1", would_fire="normal"
    )
    before = counter._value.get()

    _shadow_audit(mock_device.id, 1, RiskLevel.NORMAL)

    assert counter._value.get() == before


@pytest.mark.django_db
def test_shadow_audit_no_mismatch_when_recent_alarm_exists(facility):
    """직전 5초 안 같은 채널 AlarmRecord 있음 → mismatch 0.

    실제 PowerDevice 가 필요 — AlarmRecord.power_device FK 만족. 본 케이스만
    DB 의존 (다른 케이스는 mock_device).
    """
    from apps.alerts.models import AlarmRecord
    from apps.core.constants import AlarmType
    from apps.core.metrics import STATIC_AUDIT_MISMATCH_TOTAL
    from apps.facilities.models import PowerDevice

    device = PowerDevice.objects.create(
        device_id="t4_audit_dev",
        device_name="T4 Audit Device",
        device_code="T4AUD",
        facility=facility,
        x=0.0,
        y=0.0,
        is_active=True,
    )

    AlarmRecord.objects.create(
        facility=facility,
        alarm_type=AlarmType.POWER_OVERLOAD,
        power_device=device,
        channel=1,
        risk_level=RiskLevel.DANGER,
        source="ai",
        measured_value=10000.0,
    )

    counter = STATIC_AUDIT_MISMATCH_TOTAL.labels(
        device_id=str(device.id), channel="1", would_fire=RiskLevel.DANGER
    )
    before = counter._value.get()

    _shadow_audit(device.id, 1, RiskLevel.DANGER)

    assert counter._value.get() == before, "최근 AlarmRecord 있으면 mismatch 0"


@pytest.mark.django_db
def test_shadow_audit_mismatch_when_no_recent_alarm(mock_device):
    """직전 5초 안 같은 채널 AlarmRecord 없음 → mismatch +1."""
    from apps.core.metrics import STATIC_AUDIT_MISMATCH_TOTAL

    counter = STATIC_AUDIT_MISMATCH_TOTAL.labels(
        device_id=str(mock_device.id), channel="1", would_fire=RiskLevel.DANGER
    )
    before = counter._value.get()

    _shadow_audit(mock_device.id, 1, RiskLevel.DANGER)

    assert counter._value.get() == before + 1
