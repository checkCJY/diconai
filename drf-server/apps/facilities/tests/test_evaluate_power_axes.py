"""
전력 평가 함수 W·A·V 3축 단위 테스트 (Phase 1+2).

[회귀 커버 대상]
- evaluate_power_risk(): channel/device_id 지정 시 정격 % 환산, 미지정 시 절대값 fallback
- evaluate_current_risk(): 단방향 정격 % 환산
- evaluate_voltage_risk(): 양방향(저전압 포함) 정격 % 환산
- _evaluate_with_rated() 시맨틱: >= (정격 % path), > (legacy 절대값 path)
- graceful: 정격 미입력 / 임계치 그룹 부재 시 fallback or NORMAL

[설계 결정]
power_device fixture에 channel 1 정격 시드 후 경계값 9개 케이스 × 3축.
"""

import pytest
from django.core.cache import cache

from apps.core.constants import RiskLevel
from apps.facilities.services.threshold_service import (
    evaluate_current_risk,
    evaluate_power_risk,
    evaluate_voltage_risk,
)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def rated_device(power_device):
    """channel 1에 W=1000/A=10/V=380 정격을 시드한 PowerDevice."""
    power_device.channel_meta = {
        "1": {"name": "테스트 모터", "rated_w": 1000, "rated_a": 10, "rated_v": 380}
    }
    power_device.save()
    return power_device


# ── evaluate_power_risk (W) ──────────────────────────────────────────


@pytest.mark.django_db
def test_power_risk_pct_boundaries(rated_device):
    """정격 1000W 기준 경계값 6개 (>= 시맨틱)."""
    dev_id = rated_device.id
    assert evaluate_power_risk(790, channel=1, device_id=dev_id) == RiskLevel.NORMAL
    assert evaluate_power_risk(800, channel=1, device_id=dev_id) == RiskLevel.WARNING
    assert evaluate_power_risk(810, channel=1, device_id=dev_id) == RiskLevel.WARNING
    assert evaluate_power_risk(990, channel=1, device_id=dev_id) == RiskLevel.WARNING
    assert evaluate_power_risk(1000, channel=1, device_id=dev_id) == RiskLevel.DANGER
    assert evaluate_power_risk(1010, channel=1, device_id=dev_id) == RiskLevel.DANGER


@pytest.mark.django_db
def test_power_risk_falls_back_to_absolute_without_rated(power_device):
    """정격 미입력 채널 → power_default 절대값 fallback (기존 시맨틱 유지)."""
    assert (
        evaluate_power_risk(2200, channel=1, device_id=power_device.id)
        == RiskLevel.NORMAL
    )  # > 경계
    assert (
        evaluate_power_risk(2500, channel=1, device_id=power_device.id)
        == RiskLevel.WARNING
    )
    assert (
        evaluate_power_risk(3000, channel=1, device_id=power_device.id)
        == RiskLevel.DANGER
    )


@pytest.mark.django_db
def test_power_risk_signature_backward_compat(db):
    """기존 호출자 evaluate_power_risk(watt) — channel/device_id 없이도 동작."""
    assert evaluate_power_risk(2500) == RiskLevel.WARNING
    assert evaluate_power_risk(None) == RiskLevel.NORMAL


# ── evaluate_current_risk (A) ────────────────────────────────────────


@pytest.mark.django_db
def test_current_risk_pct_boundaries(rated_device):
    """정격 10A 기준 단방향 경계값."""
    dev_id = rated_device.id
    assert evaluate_current_risk(7.9, channel=1, device_id=dev_id) == RiskLevel.NORMAL
    assert evaluate_current_risk(8.0, channel=1, device_id=dev_id) == RiskLevel.WARNING
    assert evaluate_current_risk(9.9, channel=1, device_id=dev_id) == RiskLevel.WARNING
    assert evaluate_current_risk(10.0, channel=1, device_id=dev_id) == RiskLevel.DANGER
    assert evaluate_current_risk(11.0, channel=1, device_id=dev_id) == RiskLevel.DANGER


@pytest.mark.django_db
def test_current_risk_no_legacy_fallback(power_device):
    """전류는 power_default.current row 미존재 → 정격 없으면 NORMAL."""
    assert (
        evaluate_current_risk(100, channel=1, device_id=power_device.id)
        == RiskLevel.NORMAL
    )


# ── evaluate_voltage_risk (V) ────────────────────────────────────────


@pytest.mark.django_db
def test_voltage_risk_bidirectional_boundaries(rated_device):
    """정격 380V 양방향 경계값 — 90/95/105/110 %."""
    dev_id = rated_device.id
    # 저전압 영역
    assert evaluate_voltage_risk(338, channel=1, device_id=dev_id) == RiskLevel.DANGER
    assert (
        evaluate_voltage_risk(342, channel=1, device_id=dev_id) == RiskLevel.DANGER
    )  # 90.0%
    assert evaluate_voltage_risk(346, channel=1, device_id=dev_id) == RiskLevel.WARNING
    assert (
        evaluate_voltage_risk(361, channel=1, device_id=dev_id) == RiskLevel.WARNING
    )  # 95.0%
    assert evaluate_voltage_risk(363, channel=1, device_id=dev_id) == RiskLevel.NORMAL
    # 정상 ~ 고전압 영역
    assert evaluate_voltage_risk(380, channel=1, device_id=dev_id) == RiskLevel.NORMAL
    assert evaluate_voltage_risk(397, channel=1, device_id=dev_id) == RiskLevel.NORMAL
    assert (
        evaluate_voltage_risk(399, channel=1, device_id=dev_id) == RiskLevel.WARNING
    )  # 105.0%
    assert evaluate_voltage_risk(415, channel=1, device_id=dev_id) == RiskLevel.WARNING
    assert (
        evaluate_voltage_risk(418, channel=1, device_id=dev_id) == RiskLevel.DANGER
    )  # 110.0%
    assert evaluate_voltage_risk(420, channel=1, device_id=dev_id) == RiskLevel.DANGER


@pytest.mark.django_db
def test_voltage_risk_no_rated_returns_normal(power_device):
    """정격 미입력 → graceful NORMAL."""
    assert (
        evaluate_voltage_risk(200, channel=1, device_id=power_device.id)
        == RiskLevel.NORMAL
    )


# ── None 입력 ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_all_axes_handle_none(rated_device):
    """None 측정값 → NORMAL (통신 불능 채널)."""
    dev_id = rated_device.id
    assert evaluate_power_risk(None, channel=1, device_id=dev_id) == RiskLevel.NORMAL
    assert evaluate_current_risk(None, channel=1, device_id=dev_id) == RiskLevel.NORMAL
    assert evaluate_voltage_risk(None, channel=1, device_id=dev_id) == RiskLevel.NORMAL
