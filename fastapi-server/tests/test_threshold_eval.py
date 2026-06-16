"""calculate_power_risk() 단위 테스트 — 정격 % 환산 + 단방향/양방향 분기."""

import pytest

from power.services.threshold_eval import calculate_power_risk


@pytest.fixture(autouse=True)
def mock_channel_meta(monkeypatch):
    """모든 테스트에 채널 메타 1개 주입 — ch1: rated_w=7500, rated_a=30, rated_v=380."""
    fake = {
        "device_1": {
            "1": {"rated_w": 7500, "rated_a": 30, "rated_v": 380},
        }
    }
    monkeypatch.setattr(
        "power.services.channel_meta_cache._channel_meta_by_device", fake
    )


@pytest.mark.parametrize(
    "value,data_type,expected",
    [
        # watt — 정격 7500: 80%=6000, 100%=7500
        (4000, "watt", "normal"),  # 53%
        (6000, "watt", "warning"),  # 80% 경계
        (7000, "watt", "warning"),  # 93%
        (7500, "watt", "danger"),  # 100% 경계
        (9000, "watt", "danger"),  # 120%
        # current — 정격 30: 80%=24, 100%=30
        (10, "current", "normal"),
        (24, "current", "warning"),
        (30, "current", "danger"),
        # voltage — 정격 380, 양방향 [95-105]/[90-110]
        (380, "voltage", "normal"),  # 100%
        (361, "voltage", "warning"),  # 95% 경계 (낮은 쪽)
        (399, "voltage", "warning"),  # 105% 경계 (높은 쪽)
        (342, "voltage", "danger"),  # 90% 경계 (낮은 쪽)
        (418, "voltage", "danger"),  # 110% 경계 (높은 쪽)
        (335, "voltage", "danger"),  # 88%
    ],
)
def test_calculate_power_risk(value, data_type, expected):
    """정격 % 환산 후 watt/current/voltage 위험 등급 일치."""
    assert calculate_power_risk(value, data_type, "device_1", 1) == expected


def test_calculate_power_risk_none_value():
    """value=None → normal 반환 (센서 미수신 안전 처리)."""
    assert calculate_power_risk(None, "watt", "device_1", 1) == "normal"


def test_calculate_power_risk_no_rated_entry(monkeypatch):
    """정격 메타 미등록 채널 → normal 반환 (환산 불가 시 안전 측)."""
    monkeypatch.setattr("power.services.channel_meta_cache._channel_meta_by_device", {})
    assert calculate_power_risk(9000, "watt", "device_1", 1) == "normal"


def test_calculate_power_risk_unknown_data_type():
    """미지원 data_type → ValueError 발생 (fail-fast)."""
    with pytest.raises(ValueError, match="Unknown data_type"):
        calculate_power_risk(100, "invalid", "device_1", 1)
