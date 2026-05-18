"""combine_risk() 매트릭스 단위 테스트 (fastapi 측, DRF 와 회귀 일치).

W3.1 (un-downgrade plan §7) — 3축 매트릭스 combine_risk_3axis 추가. /review
Critical #2 의 회귀 가드: 매트릭스 12 cell + 두 AI 동의 시 격상 의도 보호.
"""

import pytest

from ai.risk_combine import combine_risk, combine_risk_3axis


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


# ---------------------------------------------------------------------------
# W3.1 — combine_risk_3axis 매트릭스 12 cell (threshold × IF × ARIMA)
# 두 AI 동의 시 한 단계 격상. ARIMA pkl 없는 채널은 arima_violation=False 호출 →
# 기존 2축 matrix 와 동일 결과 (fallback 효과).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "threshold_risk,if_prediction,arima_violation,expected",
    [
        # threshold NORMAL (4 조합)
        ("normal", "normal", False, "normal"),
        ("normal", "normal", True, "predict_warn"),
        ("normal", "anomaly", False, "predict_warn"),
        ("normal", "anomaly", True, "warning"),  # 두 AI 동의 → 격상
        # threshold WARNING (4 조합)
        ("warning", "normal", False, "caution"),
        ("warning", "normal", True, "warning"),
        ("warning", "anomaly", False, "warning"),
        ("warning", "anomaly", True, "danger"),  # 두 AI 동의 → 격상
        # threshold DANGER (4 조합 — IF/ARIMA 무관 모두 danger)
        ("danger", "normal", False, "danger"),
        ("danger", "normal", True, "danger"),
        ("danger", "anomaly", False, "danger"),
        ("danger", "anomaly", True, "danger"),
    ],
)
def test_combine_risk_3axis_matrix(
    threshold_risk, if_prediction, arima_violation, expected
):
    assert (
        combine_risk_3axis(threshold_risk, if_prediction, arima_violation) == expected
    )


def test_combine_risk_3axis_arima_false_conservative_or_equal():
    """arima_violation=False 시 3축 결과가 2축보다 같거나 한 단계 낮음 (보수적).

    plan §7 의도: 두 AI 환경에서 한 쪽만 발화 시 신뢰도 ↓ → 격상 안 함.
    예: 2축 ("warning","anomaly")=danger 인데 3축 (...,False)=warning.
    """
    _RANK = {"normal": 0, "caution": 1, "predict_warn": 1, "warning": 2, "danger": 3}
    for t in ("normal", "warning", "danger"):
        for p in ("normal", "anomaly"):
            r2 = combine_risk(t, p)
            r3 = combine_risk_3axis(t, p, False)
            assert _RANK[r3] <= _RANK[r2], (
                f"3축이 2축보다 격상되면 안 됨: ({t}, {p}, False) "
                f"→ 2축={r2}(rank {_RANK[r2]}), 3축={r3}(rank {_RANK[r3]})"
            )


def test_combine_risk_3axis_two_ai_agreement_escalates():
    """두 AI (IF anomaly + ARIMA violation) 동의 시 격상 의도 확인."""
    # threshold NORMAL: predict_warn → warning 으로 한 단계 격상
    assert combine_risk_3axis("normal", "anomaly", False) == "predict_warn"
    assert combine_risk_3axis("normal", "anomaly", True) == "warning"
    # threshold WARNING: warning → danger 로 한 단계 격상
    assert combine_risk_3axis("warning", "anomaly", False) == "warning"
    assert combine_risk_3axis("warning", "anomaly", True) == "danger"


def test_combine_risk_3axis_unknown_combination_raises():
    with pytest.raises(ValueError, match="Unknown 3axis combination"):
        combine_risk_3axis("invalid_level", "normal", False)
    with pytest.raises(ValueError, match="Unknown 3axis combination"):
        combine_risk_3axis("normal", "invalid_pred", False)
