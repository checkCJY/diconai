"""
risk_combine_service — IF 추론 + threshold 평가 결합 매트릭스

[배경]
- threshold_risk: NORMAL/WARNING/DANGER (3단계, RiskLevel)
- ml_prediction: normal/anomaly (2단계, MLAnomalyResult.Prediction)
- combined_risk: NORMAL/CAUTION/PREDICT_WARN/DANGER (4단계, MLAnomalyResult.RiskClassified)

[매트릭스 — 3×2]
threshold \\ IF | normal  | anomaly
NORMAL          | NORMAL  | PREDICT_WARN
WARNING         | CAUTION | DANGER
DANGER          | DANGER  | DANGER

[설계 결정 — plan 매트릭스 vs RiskClassified enum 정합]
plan if-data-prep-and-alarm-binding.md 원안은 (WARNING, normal) → WARNING 이지만,
combined_risk 저장 필드 MLAnomalyResult.RiskClassified 에 WARNING 이 없고 CAUTION 이
있어 치환. 의미 정합:
- CAUTION       : threshold 가 경계 진입이지만 IF 가 정상 → 약한 경보
- PREDICT_WARN  : threshold 가 정상이지만 IF 가 이상 감지 → 예측 경보
RiskClassified 4단계 모두 자연스럽게 활용 (mirror 필드 없음).
"""

from __future__ import annotations

from apps.core.constants import RiskLevel
from apps.ml.models import MLAnomalyResult

_PRED = MLAnomalyResult.Prediction
_RC = MLAnomalyResult.RiskClassified

# (threshold_risk, ml_prediction) -> combined_risk
_MATRIX: dict[tuple[str, str], str] = {
    (RiskLevel.NORMAL, _PRED.NORMAL): _RC.NORMAL,
    (RiskLevel.NORMAL, _PRED.ANOMALY): _RC.PREDICT_WARN,
    (RiskLevel.WARNING, _PRED.NORMAL): _RC.CAUTION,
    (RiskLevel.WARNING, _PRED.ANOMALY): _RC.DANGER,
    (RiskLevel.DANGER, _PRED.NORMAL): _RC.DANGER,
    (RiskLevel.DANGER, _PRED.ANOMALY): _RC.DANGER,
}


def combine_risk(threshold_risk: str, ml_prediction: str) -> str:
    """threshold_risk × ml_prediction 매트릭스 룩업 → combined_risk 반환.

    Args:
        threshold_risk: RiskLevel value (normal/warning/danger)
        ml_prediction: MLAnomalyResult.Prediction value (normal/anomaly)

    Returns:
        MLAnomalyResult.RiskClassified value (normal/caution/predict_warn/danger)

    Raises:
        ValueError: 매트릭스에 없는 조합 (운영 데이터에서 발견 시 즉시 fail-fast)
    """
    key = (threshold_risk, ml_prediction)
    if key not in _MATRIX:
        raise ValueError(
            f"Unknown combination: threshold_risk={threshold_risk!r}, "
            f"ml_prediction={ml_prediction!r}"
        )
    return _MATRIX[key]
