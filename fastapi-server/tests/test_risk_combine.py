"""combine_risk() 매트릭스 6 cell 단위 테스트 (fastapi 측, DRF 와 회귀 일치)."""

import pytest

from ai.risk_combine import combine_risk


@pytest.mark.parametrize(
    "threshold_risk,ml_prediction,expected",
    [
        # threshold NORMAL
        ("normal", "normal", "normal"),
        ("normal", "anomaly", "predict_warn"),
        # threshold WARNING
        ("warning", "normal", "caution"),
        ("warning", "anomaly", "danger"),
        # threshold DANGER (IF 결과 무관)
        ("danger", "normal", "danger"),
        ("danger", "anomaly", "danger"),
    ],
)
def test_combine_risk_matrix(threshold_risk, ml_prediction, expected):
    assert combine_risk(threshold_risk, ml_prediction) == expected


def test_combine_risk_unknown_threshold_raises():
    with pytest.raises(ValueError, match="Unknown combination"):
        combine_risk("invalid_level", "normal")


def test_combine_risk_unknown_prediction_raises():
    with pytest.raises(ValueError, match="Unknown combination"):
        combine_risk("normal", "invalid_pred")
