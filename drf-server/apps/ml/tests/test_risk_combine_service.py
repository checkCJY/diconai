"""combine_risk() 매트릭스 6 cell 단위 테스트."""

import pytest

from apps.core.constants import RiskLevel
from apps.ml.models import MLAnomalyResult
from apps.ml.services.risk_combine_service import combine_risk

_PRED = MLAnomalyResult.Prediction
_RC = MLAnomalyResult.RiskClassified


@pytest.mark.parametrize(
    "threshold_risk,ml_prediction,expected",
    [
        # threshold NORMAL
        (RiskLevel.NORMAL, _PRED.NORMAL, _RC.NORMAL),
        (RiskLevel.NORMAL, _PRED.ANOMALY, _RC.PREDICT_WARN),
        # threshold WARNING
        (RiskLevel.WARNING, _PRED.NORMAL, _RC.CAUTION),
        (RiskLevel.WARNING, _PRED.ANOMALY, _RC.DANGER),
        # threshold DANGER (IF 결과 무관)
        (RiskLevel.DANGER, _PRED.NORMAL, _RC.DANGER),
        (RiskLevel.DANGER, _PRED.ANOMALY, _RC.DANGER),
    ],
)
def test_combine_risk_matrix(threshold_risk, ml_prediction, expected):
    assert combine_risk(threshold_risk, ml_prediction) == expected


def test_combine_risk_unknown_threshold_raises():
    with pytest.raises(ValueError, match="Unknown combination"):
        combine_risk("invalid_level", _PRED.NORMAL)


def test_combine_risk_unknown_prediction_raises():
    with pytest.raises(ValueError, match="Unknown combination"):
        combine_risk(RiskLevel.NORMAL, "invalid_pred")
