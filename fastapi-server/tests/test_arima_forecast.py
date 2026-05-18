"""_arima_forecast 단위 테스트 (W3.1 + /review Critical #2 회귀 가드).

ARIMA un-downgrade plan §7 — 1-step ahead forecast + 95% CI 위반 판정.
statsmodels ARIMAResultsWrapper 의 동작을 mock 으로 격리해 핵심 로직
(actual vs CI 비교, 반환 dict 키 정확성) 검증.
"""

from types import SimpleNamespace

import numpy as np

from ai.router import _arima_forecast


def _build_mock(forecast: float, ci_low: float, ci_high: float):
    """apply() 가 self 를 반환하도록 closure 구성 (statsmodels apply 동작 모사)."""

    class _Mock:
        def apply(self, endog):  # noqa: ARG002
            return self

        def get_forecast(self, steps):  # noqa: ARG002
            return SimpleNamespace(
                predicted_mean=np.array([forecast]),
                conf_int=lambda alpha: np.array([[ci_low, ci_high]]),
            )

    return _Mock()


# ---------------------------------------------------------------------------
# 반환 키 정확성
# ---------------------------------------------------------------------------


def test_arima_forecast_returns_expected_keys():
    mock = _build_mock(forecast=100.0, ci_low=80.0, ci_high=120.0)
    result = _arima_forecast([90.0, 95.0, 105.0, 110.0], mock)
    assert set(result.keys()) == {
        "forecast",
        "ci_lower",
        "ci_upper",
        "actual",
        "is_violation",
    }


def test_arima_forecast_values():
    mock = _build_mock(forecast=100.0, ci_low=80.0, ci_high=120.0)
    result = _arima_forecast([90.0, 95.0, 105.0, 110.0], mock)
    assert result["forecast"] == 100.0
    assert result["ci_lower"] == 80.0
    assert result["ci_upper"] == 120.0
    assert result["actual"] == 110.0  # 마지막 값


# ---------------------------------------------------------------------------
# is_violation 판정 — actual vs CI 비교
# ---------------------------------------------------------------------------


def test_arima_forecast_violation_false_when_actual_within_ci():
    mock = _build_mock(forecast=100.0, ci_low=80.0, ci_high=120.0)
    result = _arima_forecast([90.0, 110.0], mock)  # actual=110, CI=[80,120]
    assert result["is_violation"] is False


def test_arima_forecast_violation_true_when_actual_above_ci_upper():
    mock = _build_mock(forecast=100.0, ci_low=80.0, ci_high=120.0)
    result = _arima_forecast([90.0, 150.0], mock)  # actual=150 > 120
    assert result["is_violation"] is True


def test_arima_forecast_violation_true_when_actual_below_ci_lower():
    mock = _build_mock(forecast=100.0, ci_low=80.0, ci_high=120.0)
    result = _arima_forecast([90.0, 50.0], mock)  # actual=50 < 80
    assert result["is_violation"] is True


def test_arima_forecast_violation_boundary_equal_to_ci_lower():
    """경계값 actual == ci_lower 시 violation=False (< 비교라 포함)."""
    mock = _build_mock(forecast=100.0, ci_low=80.0, ci_high=120.0)
    result = _arima_forecast([90.0, 80.0], mock)
    assert result["is_violation"] is False


def test_arima_forecast_violation_boundary_equal_to_ci_upper():
    """경계값 actual == ci_upper 시 violation=False (> 비교라 포함)."""
    mock = _build_mock(forecast=100.0, ci_low=80.0, ci_high=120.0)
    result = _arima_forecast([90.0, 120.0], mock)
    assert result["is_violation"] is False


# ---------------------------------------------------------------------------
# 타입 강제 — float 변환 확인
# ---------------------------------------------------------------------------


def test_arima_forecast_returns_python_float_not_numpy():
    """반환값이 Python float 인지 확인 (JSON 직렬화 안전 — payload 전송 대비)."""
    mock = _build_mock(forecast=100.0, ci_low=80.0, ci_high=120.0)
    result = _arima_forecast([90.0, 110.0], mock)
    assert isinstance(result["forecast"], float)
    assert isinstance(result["ci_lower"], float)
    assert isinstance(result["ci_upper"], float)
    assert isinstance(result["actual"], float)
    assert isinstance(result["is_violation"], bool)
