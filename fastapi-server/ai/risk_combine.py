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


# ---------------------------------------------------------------------------
# W3 — 3축 매트릭스 (skill/plan/power-ai-un-downgrade-phase2-apply.md §7).
# 두 AI 모델 (IF + ARIMA) 동의 시 한 단계 격상 / 단일 AI 만 발화 시 보수적.
# ⚠ 2축 matrix 와 다름 — 단일 AI 발화 시 본 3축이 한 단계 낮음:
#   - 2축 ("warning", "anomaly") = "danger" (IF 단독으로 격상)
#   - 3축 ("warning", "anomaly", False) = "warning" (두 AI 동의 시만 격상)
# 의도: 두 AI 환경에서 한 쪽만 발화 시 신뢰도 ↓ 반영. ARIMA pkl 없는 채널은
# caller 가 arima_violation=False 호출 → 본 3축 보수적 결과 적용 (2축 fallback X).
# ---------------------------------------------------------------------------

_MATRIX_3AXIS: dict[tuple[str, str, bool], str] = {
    # (threshold, if_prediction, arima_violation) → combined
    ("normal", "normal", False): "normal",
    ("normal", "normal", True): "predict_warn",
    ("normal", "anomaly", False): "predict_warn",
    ("normal", "anomaly", True): "warning",
    ("warning", "normal", False): "caution",
    ("warning", "normal", True): "warning",
    ("warning", "anomaly", False): "warning",
    ("warning", "anomaly", True): "danger",
    ("danger", "normal", False): "danger",
    ("danger", "normal", True): "danger",
    ("danger", "anomaly", False): "danger",
    ("danger", "anomaly", True): "danger",
}


def combine_risk_3axis(
    threshold_risk: str,
    if_prediction: str,
    arima_violation: bool,
) -> str:
    """3축 결합 — threshold × IF × ARIMA → combined_risk (W3 신규).

    두 AI 모델 동의 시 한 단계 격상 (warning → danger 등). 단일 발화 시
    기존 2축 매트릭스와 같은 결과.

    Args:
        threshold_risk: "normal" | "warning" | "danger"
        if_prediction: "normal" | "anomaly"
        arima_violation: True 면 ARIMA forecast 95% 신뢰구간 위반, False 면 정상범위

    Raises:
        ValueError: 매트릭스에 없는 조합 (운영 데이터에서 발견 시 즉시 fail-fast)
    """
    key = (threshold_risk, if_prediction, arima_violation)
    if key not in _MATRIX_3AXIS:
        raise ValueError(
            f"Unknown 3axis combination: threshold_risk={threshold_risk!r}, "
            f"if_prediction={if_prediction!r}, arima_violation={arima_violation!r}"
        )
    return _MATRIX_3AXIS[key]
