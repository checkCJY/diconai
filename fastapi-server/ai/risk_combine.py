"""
risk_combine — fastapi 측 combine_risk 매트릭스 (트랙 1 v2 — fastapi 중심)

[배경]
가스/전력 추론은 fastapi 안에서 실시간 처리 (엣지게이트웨이 → fastapi → 알람).
DRF 측 동일 매트릭스 (apps.ml.services.risk_combine_service) 와 회귀 일치 필수.

[매트릭스 — 3×2]
threshold \\ IF | normal  | anomaly
NORMAL          | NORMAL  | PREDICT_WARN
WARNING         | CAUTION | DANGER
DANGER          | DANGER  | DANGER

DRF 는 MLAnomalyResult.RiskClassified enum 기반, fastapi 는 string literal 사용.
값 (소문자) 은 양측 동일 — 통신 페이로드 호환.
"""

from __future__ import annotations

# (threshold_risk, ml_prediction) -> combined_risk
_MATRIX: dict[tuple[str, str], str] = {
    ("normal", "normal"): "normal",
    ("normal", "anomaly"): "predict_warn",
    ("warning", "normal"): "caution",
    ("warning", "anomaly"): "danger",
    ("danger", "normal"): "danger",
    ("danger", "anomaly"): "danger",
}


def combine_risk(threshold_risk: str, ml_prediction: str) -> str:
    """threshold_risk × ml_prediction → combined_risk 매트릭스 룩업.

    Args:
        threshold_risk: "normal" | "warning" | "danger" (RiskLevel value)
        ml_prediction: "normal" | "anomaly" (MLAnomalyResult.Prediction value)

    Returns:
        "normal" | "caution" | "predict_warn" | "danger"
        (MLAnomalyResult.RiskClassified value)

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
