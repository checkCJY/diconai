"""change_point_service — STEP E (Change Point) 전력 단독.

상위 plan: skill/plan/anomaly-detection-zscore-changepoint.md §3.3
적용 plan: skill/plan/power-zscore-changepoint-apply.md §E1

STEP 4·STEP 5 권고 two-window 비교 방식 (의존성 0, ruptures 미사용). 판단 흐름:

  1) prev = window[:W] / curr = window[W:2W]
  2) mean_shift = |curr_mean - prev_mean| / (prev_std + EPS)
  3) std_ratio = (curr_std + EPS) / (prev_std + EPS)
  4) is_change = (mean_shift >= MEAN_K) or (std_ratio >= STD_K) or (std_ratio <= 1/STD_K)
  5) 상태 머신 STABLE→SHIFT 전이 시점에만 True 반환 (중복 발화 방지).
     SHIFT→STABLE 복귀 시 상태만 갱신 (BACK_TO_STABLE, 발화 X).

[설계 결정]
- CP 윈도우는 IF 윈도우 (power_service._power_windows maxlen=30) 와 분리.
  Why: IF 추론은 최근 30개 슬라이딩, CP 는 prev 30 vs curr 30 비교 (2W=60) 필요.
  How: _cp_windows: dict[(channel, data_type), deque(maxlen=60)] 모듈 단위.
- 상태 머신은 (channel, data_type) 단위 dict — fastapi 재시작 시 STABLE 로 초기화.
- 임계치 (MEAN_K=3.0, STD_K=2.0) 는 STEP 4 권고 초기값. 시연 후 튜닝.
"""

from collections import defaultdict, deque

import numpy as np

_W = 30  # 단일 비교 구간 길이 (prev / curr 각각)
_CP_WINDOW = 2 * _W  # 60 = prev 30 + curr 30
_MEAN_K = 3.0  # 평균 변화 민감도 (prev_std 대비)
_STD_K = 2.0  # 분산 변화 민감도 (2배만 커져도 의미 — STEP 4 권고)
_EPS = 1e-9  # 0 나누기 안전핀

# 채널별 CP 윈도우·상태. fastapi 프로세스 메모리, 재시작 시 자연 초기화.
_cp_windows: dict[tuple[int, str], deque] = defaultdict(
    lambda: deque(maxlen=_CP_WINDOW)
)
_cp_states: dict[tuple[int, str], str] = defaultdict(lambda: "STABLE")


def detect_change_point(key: tuple[int, str], value: float) -> tuple[bool, dict]:
    """Two-window CP 탐지 — prev[0:W] vs curr[W:2W] 평균/분산 비교.

    상태 머신 STABLE → SHIFT 전이 시점 (CHANGE_POINT 발화) 만 True 반환.
    SHIFT 지속 중에는 False (중복 발화 방지). BACK_TO_STABLE 시 상태만 복귀.

    Args:
        key: (channel, data_type) 채널 단위 식별자. _cp_windows / _cp_states
             둘의 키. 채널별 독립 윈도우·상태 유지.
        value: 현재 측정값 (deque 누적용).

    Returns:
        (is_change_point, meta)
        - is_change_point=True → 본 틱이 CHANGE_POINT (STABLE→SHIFT 전이)
        - meta = {"mean_shift": float, "std_ratio": float, "state": "STABLE"|"SHIFT"}
        - 윈도우 누적 < _CP_WINDOW 면 (False, {}) — 통계 불안정 보호.
    """
    win = _cp_windows[key]
    win.append(float(value))
    if len(win) < _CP_WINDOW:
        return False, {}

    arr = np.array(win, dtype=float)
    prev = arr[:_W]
    curr = arr[_W:]
    prev_mean = float(prev.mean())
    prev_std = float(prev.std())
    curr_mean = float(curr.mean())
    curr_std = float(curr.std())

    mean_shift = abs(curr_mean - prev_mean) / (prev_std + _EPS)
    std_ratio = (curr_std + _EPS) / (prev_std + _EPS)
    is_change = (
        mean_shift >= _MEAN_K or std_ratio >= _STD_K or std_ratio <= 1.0 / _STD_K
    )

    prev_state = _cp_states[key]
    is_change_point = False
    if prev_state == "STABLE" and is_change:
        _cp_states[key] = "SHIFT"
        is_change_point = True
    elif prev_state == "SHIFT" and not is_change:
        _cp_states[key] = "STABLE"

    return is_change_point, {
        "mean_shift": mean_shift,
        "std_ratio": std_ratio,
        "state": _cp_states[key],
    }


def reset_state(key: tuple[int, str] | None = None) -> None:
    """채널 단위 또는 전체 CP 상태 초기화 — 주로 테스트 격리용 (코드리뷰 §3.3).

    운영 코드는 사용 X — fastapi 재시작 시 모듈 단위 dict 가 자연 초기화 됨.

    Args:
        key: (channel, data_type) — 특정 채널만 초기화. None 이면 전체.
    """
    if key is None:
        _cp_windows.clear()
        _cp_states.clear()
    else:
        _cp_windows.pop(key, None)
        _cp_states.pop(key, None)
