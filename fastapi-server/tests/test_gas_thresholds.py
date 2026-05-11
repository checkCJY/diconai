"""
가스 임계치 분기 스모크 테스트 (PR-F).

[회귀 커버]
- evaluate_single_gas: 9종 분기 (o2 분기 포함)
- DRF 측 threshold_default.json과 값 일치 검증 (단일 진실 공급원 정책 일관)

[단일 진실 공급원 정책]
DRF가 GasData.save() 시 raw 측정값으로 위험도 재계산. fastapi 측 risk는 더미 생성용
(또는 표시용 fallback). 양측 임계치 값이 일치해야 분기 결과 동일.
"""

import pytest

from core.gas_thresholds import (
    GAS_THRESHOLDS,
    calculate_gas_status,
    calculate_individual_risks,
    evaluate_single_gas,
)


@pytest.mark.parametrize(
    "gas,value,expected",
    [
        ("co", 10, "normal"),
        ("co", 30, "warning"),
        ("co", 200, "danger"),
        ("h2s", 5, "normal"),
        ("h2s", 12, "warning"),
        ("h2s", 20, "danger"),
        ("o2", 20, "normal"),
        ("o2", 17, "warning"),
        ("o2", 15, "danger"),
        ("voc", 0.3, "normal"),
        ("voc", 0.7, "warning"),
        ("voc", 1.5, "danger"),
    ],
)
def test_evaluate_single_gas_matches_drf_thresholds(gas, value, expected):
    """단일 가스 분기 — DRF threshold_default.json 9종과 일치."""
    assert evaluate_single_gas(gas, value) == expected


def test_calculate_gas_status_returns_max_risk():
    """전체 상태는 최고 위험도 반환."""
    gas_values = {"co": 10, "h2s": 12, "o2": 20}  # warning, normal
    assert calculate_gas_status(gas_values) == "warning"

    gas_values_danger = {"co": 250, "h2s": 5}
    assert calculate_gas_status(gas_values_danger) == "danger"


def test_calculate_individual_risks_excludes_lel():
    """lel 키가 들어와도 결과 dict에는 미포함 (센서 정의서 9종)."""
    gas_values = {"co": 10, "lel": 5, "h2s": 5}
    risks = calculate_individual_risks(gas_values)
    assert "co_risk" in risks
    assert "h2s_risk" in risks
    assert "lel_risk" not in risks


def test_gas_thresholds_keys_match_sensor_spec():
    """GAS_THRESHOLDS 9종 — 센서 정의서(2026-04-01) 일관."""
    expected = {"co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"}
    assert set(GAS_THRESHOLDS.keys()) == expected
