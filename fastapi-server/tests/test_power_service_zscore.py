"""_zscore_check 단위 테스트 (D2 / plan §D2 — power-zscore-changepoint-apply).

STEP D Z-score 통계 이상 판정. window=_INFERENCE_WINDOW(30) deque (IF 추론 윈도우
재활용) 기준 6 케이스 — 누적 미충족 / 정상 / +튐 / -튐 / std=0 (EPS 안전핀) /
threshold 경계.

본 커밋(D2)은 헬퍼 산출만 추가. 발화 영향은 §F (combine_risk_5axis) 진입 시.
"""

from collections import deque

from power.services.power_service import _INFERENCE_WINDOW, _zscore_check


def _make_window(values: list[float]) -> deque:
    """maxlen=_INFERENCE_WINDOW deque 헬퍼."""
    win: deque = deque(maxlen=_INFERENCE_WINDOW)
    for v in values:
        win.append(v)
    return win


def test_zscore_window_below_min_returns_false():
    """window 누적이 _INFERENCE_WINDOW 미만이면 False (초반 통계 불안정 보호)."""
    win = _make_window([100.0] * (_INFERENCE_WINDOW - 1))
    assert _zscore_check(win, 999.0) is False


def test_zscore_normal_value_returns_false():
    """평소 범위 안 값은 False (z=2.91, threshold=3 미달)."""
    # mean=100, std≈0.516 — value=101.5 → z≈2.91
    win = _make_window([100.0] * 28 + [98.0, 102.0])
    assert _zscore_check(win, 101.5, threshold=3.0) is False


def test_zscore_positive_spike_returns_true():
    """+ 방향 튐 → True (z≈19)."""
    win = _make_window([100.0] * 28 + [98.0, 102.0])
    assert _zscore_check(win, 110.0, threshold=3.0) is True


def test_zscore_negative_spike_returns_true():
    """- 방향 튐 → True (절대값 |z| 기준)."""
    win = _make_window([100.0] * 28 + [98.0, 102.0])
    assert _zscore_check(win, 90.0, threshold=3.0) is True


def test_zscore_std_zero_eps_no_division_error():
    """std=0 (완전 동일값 윈도우) — EPS 안전핀으로 분모 폭발 없이 동작.

    동일값 윈도우 + value=윈도우값 → z≈0 (False).
    동일값 윈도우 + value≠윈도우값 → z 매우 큼 (True).
    """
    win = _make_window([50.0] * _INFERENCE_WINDOW)
    assert _zscore_check(win, 50.0) is False
    assert _zscore_check(win, 51.0) is True


def test_zscore_threshold_param_overridable():
    """threshold 파라미터 — 기본 3.0, 호출자가 낮춰 호출하면 더 민감."""
    # mean=100, std≈0.516 — value=101.5 → z≈2.91
    win = _make_window([100.0] * 28 + [98.0, 102.0])
    # threshold=3.0 → False (z<3)
    assert _zscore_check(win, 101.5, threshold=3.0) is False
    # threshold=2.5 → True (z>2.5)
    assert _zscore_check(win, 101.5, threshold=2.5) is True
