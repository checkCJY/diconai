"""combine_risk() 매트릭스 단위 테스트 (fastapi 측, DRF 와 회귀 일치).

W3.1 (un-downgrade plan §7) — 3축 매트릭스 combine_risk_3axis 추가. /review
Critical #2 의 회귀 가드: 매트릭스 12 cell + 두 AI 동의 시 격상 의도 보호.

§F (plan power-zscore-changepoint-apply §F) — 5축 우선순위 함수
combine_risk_5axis 추가. base=combine_risk_3axis 위임으로 3축 회귀 보존.
"""

import pytest

from ai.risk_combine import combine_risk, combine_risk_3axis, combine_risk_5axis


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


# ---------------------------------------------------------------------------
# §F — combine_risk_5axis 는 (combined, escalation_source) 튜플 반환.
# escalation_source = "zscore" | "change_point" | "" — base=normal 일 때 z/cp
# 가 실제 격상에 기여하면 라벨, 아니면 "" (caller 의 algorithm_source 결정
# 흐름이 사용). 코드리뷰 2026-05-19 §2.1 보강.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "threshold,if_pred,arima,z,cp,expected_combined,expected_source",
    [
        # 회귀 — 5축 모두 False 면 3축 결과 + source=""
        ("normal", "normal", False, False, False, "normal", ""),
        ("warning", "normal", False, False, False, "caution", ""),
        ("danger", "normal", False, False, False, "danger", ""),
        # base=normal + Z-score → predict_warn + source=zscore
        ("normal", "normal", False, True, False, "predict_warn", "zscore"),
        # base=normal + CP → predict_warn + source=change_point
        ("normal", "normal", False, False, True, "predict_warn", "change_point"),
        # base=normal + 둘 다 → predict_warn + source=change_point (CP 우선)
        ("normal", "normal", False, True, True, "predict_warn", "change_point"),
        # base=caution + Z-score → caution 유지 + source="" (z 격상 기여 X)
        ("warning", "normal", False, True, False, "caution", ""),
        ("warning", "normal", False, False, True, "caution", ""),
        # base=danger + 모든 5축 → danger + source="" (z/cp 격상 기여 X)
        ("danger", "anomaly", True, True, True, "danger", ""),
        # 두 AI 동의 격상 (base=warning) + Z-score → warning + source=""
        ("normal", "anomaly", True, True, False, "warning", ""),
        # IF 단독 격상 (base=predict_warn) + CP → predict_warn + source=""
        ("normal", "anomaly", False, False, True, "predict_warn", ""),
        # ARIMA 단독 (base=predict_warn) + Z-score → predict_warn + source=""
        ("normal", "normal", True, True, False, "predict_warn", ""),
    ],
)
def test_combine_risk_5axis_priority_matrix(
    threshold, if_pred, arima, z, cp, expected_combined, expected_source
):
    combined, source = combine_risk_5axis(threshold, if_pred, arima, z, cp)
    assert combined == expected_combined
    assert source == expected_source


def test_combine_risk_5axis_preserves_3axis_regression():
    """base 인 combine_risk_3axis 결과를 그대로 반환 (회귀 가드).

    Z-score / CP 5축 입력이 둘 다 False 일 때 5축 결과 == 3축 + source="".
    """
    for t in ("normal", "warning", "danger"):
        for p in ("normal", "anomaly"):
            for a in (True, False):
                expected = combine_risk_3axis(t, p, a)
                actual, source = combine_risk_5axis(t, p, a, False, False)
                assert (
                    actual == expected
                ), f"5축 회귀 깨짐: ({t}, {p}, {a}) 3축={expected} 5축={actual}"
                assert (
                    source == ""
                ), f"z/cp=False 일 때 source 는 빈 문자열이어야 함: {source!r}"


def test_combine_risk_5axis_zscore_only_escalates_base_normal():
    """Z-score 격상은 base=normal 일 때만 — 다른 base 면 무시 (우선순위 매핑)."""
    combined, source = combine_risk_5axis("normal", "normal", False, True, False)
    assert combined == "predict_warn"
    assert source == "zscore"
    # base=caution (warning + IF normal) → caution 유지 + source="" (z 기여 X)
    combined, source = combine_risk_5axis("warning", "normal", False, True, False)
    assert combined == "caution"
    assert source == ""


def test_combine_risk_5axis_cp_only_escalates_base_normal():
    """CP 격상도 같은 우선순위 — base=normal 일 때만 predict_warn + source=cp."""
    combined, source = combine_risk_5axis("normal", "normal", False, False, True)
    assert combined == "predict_warn"
    assert source == "change_point"
    combined, source = combine_risk_5axis("danger", "normal", False, False, True)
    assert combined == "danger"
    assert source == ""  # base=danger 면 cp 격상 기여 X


def test_combine_risk_5axis_zcp_both_true_prefers_change_point():
    """z + cp 둘 다 True 면 source=change_point (CP 우선 — algorithm_source priority 일치)."""
    combined, source = combine_risk_5axis("normal", "normal", False, True, True)
    assert combined == "predict_warn"
    assert source == "change_point"


def test_combine_risk_5axis_3axis_unknown_bubbles_up():
    """잘못된 input → base 호출에서 ValueError 그대로 bubble up (fail-fast)."""
    with pytest.raises(ValueError, match="Unknown 3axis combination"):
        combine_risk_5axis("invalid_level", "normal", False, False, False)
