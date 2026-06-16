"""quality_guard 단위 테스트 (W0 + /review Critical #2 회귀 가드).

ARIMA un-downgrade plan §3 (W0) — process_anomaly_inference 진입부의 quality
검사. 통신 단절 / 센서 오버플로우 / 센서 고정 고장이 IF 학습/추론 윈도우에
흡수되는 것 방지하는 핵심 함수들.
"""

from collections import deque

import pytest

from power.services.quality_guard import (
    classify_sensor_status,
    is_inference_stuck,
)


# ---------------------------------------------------------------------------
# classify_sensor_status — None / -1 / overflow 판정
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,data_type,expected",
    [
        # 정상값 (None 반환 = 추론 가능)
        (1000.0, "watt", None),
        (50.0, "current", None),
        (380.0, "voltage", None),
        (0.0, "watt", None),  # 0 은 정상 값 (센서 미수신 값 아님 — CLAUDE.md 참조)
        # comm_failure — None / -1
        (None, "watt", "comm_failure"),
        (-1, "watt", "comm_failure"),
        (-1.0, "current", "comm_failure"),
        # 잘못된 타입 → comm_failure (TypeError/ValueError 처리)
        ("invalid", "watt", "comm_failure"),
        # overflow — UPPER_BOUND_BY_TYPE 초과
        (50001, "watt", "sensor_fault_overflow"),  # watt 상한 50000
        (200.1, "current", "sensor_fault_overflow"),  # current 상한 200
        (600.5, "voltage", "sensor_fault_overflow"),  # voltage 상한 600
        # overflow 경계 (정확히 상한값은 통과)
        (50000.0, "watt", None),
        (200.0, "current", None),
    ],
)
def test_classify_sensor_status(value, data_type, expected):
    """값/타입별 센서 상태 판정 (정상/comm_failure/overflow) 일치."""
    assert classify_sensor_status(value, data_type) == expected


def test_classify_sensor_status_unknown_data_type_returns_none():
    """data_type 이 UPPER_BOUND_BY_TYPE 에 없으면 overflow 검사 skip (정상 통과)."""
    # 정상값이라면 None 반환 (data_type 무관 None/-1 만 comm_failure)
    assert classify_sensor_status(1000.0, "unknown_type") is None
    assert classify_sensor_status(99999.0, "unknown_type") is None


# ---------------------------------------------------------------------------
# is_inference_stuck — 윈도우 가득 + 모든 값 동일 판정
# ---------------------------------------------------------------------------


def test_is_inference_stuck_full_window_all_same_returns_true():
    """윈도우 가득 + 모든 값 동일 → stuck (센서 고정 고장)."""
    history = deque([999.0] * 30, maxlen=30)
    assert is_inference_stuck(history) is True


def test_is_inference_stuck_full_window_varying_values_returns_false():
    """윈도우 가득이지만 값이 다양 → 정상 (stuck 아님)."""
    history = deque([float(i) for i in range(30)], maxlen=30)
    assert is_inference_stuck(history) is False


def test_is_inference_stuck_partial_window_returns_false():
    """윈도우 미충족 (warmup 구간) → 항상 false (정상 추론 회피 안 함)."""
    history = deque([1000.0] * 10, maxlen=30)  # 10/30 = 미충족
    assert is_inference_stuck(history) is False


def test_is_inference_stuck_full_window_one_outlier_returns_false():
    """1개 값만 다르면 stuck 아님 (전체 동일성 요구)."""
    values = [1000.0] * 29 + [1001.0]
    history = deque(values, maxlen=30)
    assert is_inference_stuck(history) is False


def test_is_inference_stuck_maxlen_none_returns_false():
    """maxlen 없는 deque 는 stuck 판정 skip (정의되지 않은 경계 → 보수적으로 false)."""
    history = deque([1000.0] * 30)  # maxlen 미지정
    assert is_inference_stuck(history) is False


def test_is_inference_stuck_full_window_with_zeros_returns_true():
    """모든 값이 0 인 경우도 stuck (센서 일관 고정)."""
    history = deque([0.0] * 30, maxlen=30)
    assert is_inference_stuck(history) is True
