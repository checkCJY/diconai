# power/services/zscore_anomaly.py — 전력 Z-score 이상 판정 헬퍼
#
# 데이터 흐름:
#   IN  : anomaly_inference.process_anomaly_inference 가 채널별 슬라이딩 윈도우
#         (_power_windows[(channel, data_type)] = deque(maxlen=_INFERENCE_WINDOW))
#         에 측정값을 누적한 뒤 _zscore_check 호출
#   OUT : (is_anomaly, abs_z) — 5축 결합 (risk_combine.combine_risk_5axis) 의 Z 축 입력
from collections import defaultdict, deque

import numpy as np

# IF · ARIMA · Z-score 공통 슬라이딩 윈도우 길이 (1Hz 기준 30초).
# fastapi 재시작 시 초기화되는 무상태 in-memory 누적.
_INFERENCE_WINDOW = 30

_power_windows: dict[tuple[int, str], deque] = defaultdict(
    lambda: deque(maxlen=_INFERENCE_WINDOW)
)


def _zscore_check(
    window: deque, value: float, threshold: float = 3.0
) -> tuple[bool, float]:
    """슬라이딩 윈도우의 평균·표준편차 기반 Z-score 이상 판정.

    |z| >= threshold 면 통계 이상 (predict_warn 격상 후보). 윈도우 길이가
    _INFERENCE_WINDOW 미만이면 초반 통계 불안정으로 (False, 0.0) 반환.

    Args:
        window: 최근 N개 값 deque. 현재 value 가 이미 append 된 상태로
            전달되어도 무방 — pandas rolling 패턴 (N=30 에서 1/N 영향 미미).
        value: 현재 측정값.
        threshold: 발화 |z| 임계 (기본 3σ).

    Returns:
        (is_anomaly, abs_z) — abs_z 는 로깅용 |z|.
    """
    if len(window) < _INFERENCE_WINDOW:
        return False, 0.0
    arr = np.array(window, dtype=float)
    mean = arr.mean()
    std = arr.std()
    z = abs(value - mean) / (std + 1e-9)  # std=0 분모 폭발 방지
    return bool(z >= threshold), float(z)
