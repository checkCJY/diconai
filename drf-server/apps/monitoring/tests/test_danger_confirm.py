"""danger 2틱 confirm 검증 — 단일 틱 센서 스파이크/인러시 false danger 억제.

- confirm_consecutive: 연속 카운트 헬퍼 (deterministic, redis 불필요).
- gas danger: 1틱 미발화 / 연속 2틱째 발화 / 비-danger 틱에 리셋.
- power danger: watt 축에서만 카운트 → 비-watt 축 danger 는 발화 안 함, watt 2틱째 발화.

try_transition / is_ai_mute_active / fire_*_task 는 raw redis·Celery 의존이라 patch.
DANGER_CONFIRM_TICKS=2 로 고정해 검증.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.core.cache import cache

from apps.alerts.services.alarm_dedupe import confirm_consecutive
from apps.core.constants import RiskLevel


def test_confirm_consecutive_counts_and_resets():
    """2틱 임계 — 1틱 False, 2틱 True, delete 후 리셋, threshold 1 은 즉시."""
    cache.clear()
    key = "t:confirm:co"
    assert confirm_consecutive(key, 2, 60) is False  # 1틱
    assert confirm_consecutive(key, 2, 60) is True  # 2틱 → 확정
    cache.delete(key)  # 스트릭 끊김
    assert confirm_consecutive(key, 2, 60) is False  # 리셋 후 다시 1틱
    assert (
        confirm_consecutive("t:confirm:imm", 1, 60) is True
    )  # threshold 1 = 즉시(기존 동작)


# ── gas ──────────────────────────────────────────────────────


def _patch_gas(monkeypatch):
    fire_delay = MagicMock()
    monkeypatch.setattr(
        "apps.monitoring.services.gas_alarm.try_transition", lambda *a, **k: True
    )
    monkeypatch.setattr(
        "apps.monitoring.services.gas_alarm.fire_danger_alarm_task",
        MagicMock(delay=fire_delay),
    )
    return fire_delay


@pytest.mark.django_db
def test_gas_danger_requires_two_ticks(gas_sensor, settings, monkeypatch):
    settings.DANGER_CONFIRM_TICKS = 2
    cache.clear()
    fire_delay = _patch_gas(monkeypatch)
    from apps.monitoring.services import gas_alarm

    # no2 는 AI 미가드 가스 → is_gas_ai_mute_active 호출 안 함 (redis 회피)
    gd = SimpleNamespace(gas_sensor=gas_sensor, no2=10.0, no2_risk="danger")

    gas_alarm.trigger_gas_alarms(gd)
    assert fire_delay.call_count == 0  # 1틱 — 미발화
    gas_alarm.trigger_gas_alarms(gd)
    assert fire_delay.call_count == 1  # 연속 2틱 — 발화


@pytest.mark.django_db
def test_gas_danger_streak_resets_on_normal(gas_sensor, settings, monkeypatch):
    settings.DANGER_CONFIRM_TICKS = 2
    cache.clear()
    fire_delay = _patch_gas(monkeypatch)
    from apps.monitoring.services import gas_alarm

    danger = SimpleNamespace(gas_sensor=gas_sensor, no2=10.0, no2_risk="danger")
    normal = SimpleNamespace(gas_sensor=gas_sensor, no2=1.0, no2_risk="normal")

    gas_alarm.trigger_gas_alarms(danger)  # dcount=1
    gas_alarm.trigger_gas_alarms(normal)  # 리셋
    gas_alarm.trigger_gas_alarms(danger)  # dcount=1 (리셋됐으므로 다시 1)
    assert fire_delay.call_count == 0  # 2연속 아님 → 미발화 (리셋 동작 확인)


# ── power ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_power_danger_watt_requires_two_ticks(power_device, settings, monkeypatch):
    settings.DANGER_CONFIRM_TICKS = 2
    cache.clear()
    fire_delay = MagicMock()
    monkeypatch.setattr(
        "apps.monitoring.services.power_alarm.evaluate_power_risk",
        lambda *a, **k: RiskLevel.DANGER,
    )
    monkeypatch.setattr(
        "apps.monitoring.services.power_alarm.try_transition", lambda *a, **k: True
    )
    monkeypatch.setattr(
        "apps.monitoring.services.power_alarm.is_ai_mute_active", lambda *a, **k: False
    )
    monkeypatch.setattr(
        "apps.monitoring.services.power_alarm.fire_power_danger_task",
        MagicMock(delay=fire_delay),
    )
    from apps.monitoring.services import power_alarm

    objs = [SimpleNamespace(channel=1, value=4000.0, data_type="watt")]
    power_alarm.trigger_power_alarms(objs, power_device)
    assert fire_delay.call_count == 0  # watt 1틱
    power_alarm.trigger_power_alarms(objs, power_device)
    assert fire_delay.call_count == 1  # watt 연속 2틱 — 발화


@pytest.mark.django_db
def test_power_danger_non_watt_axis_does_not_fire(power_device, settings, monkeypatch):
    """current 축 danger 는 발화 안 함 — danger 확정은 watt 도착 때만 (사이클당 1회)."""
    settings.DANGER_CONFIRM_TICKS = 2
    cache.clear()
    fire_delay = MagicMock()
    monkeypatch.setattr(
        "apps.monitoring.services.power_alarm.evaluate_current_risk",
        lambda *a, **k: RiskLevel.DANGER,
    )
    monkeypatch.setattr(
        "apps.monitoring.services.power_alarm.try_transition", lambda *a, **k: True
    )
    monkeypatch.setattr(
        "apps.monitoring.services.power_alarm.is_ai_mute_active", lambda *a, **k: False
    )
    monkeypatch.setattr(
        "apps.monitoring.services.power_alarm.fire_power_danger_task",
        MagicMock(delay=fire_delay),
    )
    from apps.monitoring.services import power_alarm

    objs = [SimpleNamespace(channel=1, value=30.0, data_type="current")]
    power_alarm.trigger_power_alarms(objs, power_device)
    power_alarm.trigger_power_alarms(objs, power_device)
    power_alarm.trigger_power_alarms(objs, power_device)
    assert fire_delay.call_count == 0  # 비-watt 축은 confirm 카운트 안 함 → 미발화
