"""change_point_service 단위 테스트 (E1 / plan §E1).

STEP E two-window CP 탐지. 5 케이스 — 윈도우 미충족 / 안정 시계열 / 평균 shift
/ BACK_TO_STABLE / 분산 단독 변화. 상태 머신 (STABLE↔SHIFT) 의 중복 발화 방지·
복귀 동작 회귀 가드.

본 commit (E1) 은 산출만 추가 — 5축 결합·algorithm_source 반영은 §F 진입 시.
"""

import pytest

from power.services.change_point_service import (
    _cp_states,
    _cp_windows,
    detect_change_point,
)


@pytest.fixture(autouse=True)
def _reset_state():
    """모듈 단위 dict 가 테스트 간 누적되지 않도록 매 테스트 시작 시 비움."""
    _cp_windows.clear()
    _cp_states.clear()
    yield
    _cp_windows.clear()
    _cp_states.clear()


KEY = (1, "watt")


def test_change_point_window_below_min_returns_false():
    """윈도우 누적 < 60 → False / 빈 meta (통계 불안정 보호)."""
    for _ in range(59):
        is_cp, meta = detect_change_point(KEY, 100.0)
        assert is_cp is False
        assert meta == {}


def test_change_point_stable_series_no_fire():
    """안정 시계열 60개 → CHANGE_POINT 발화 0, state=STABLE."""
    fired = []
    for i in range(60):
        is_cp, _ = detect_change_point(KEY, 99.5 + (i % 2))  # 99.5 / 100.5
        fired.append(is_cp)
    assert all(not f for f in fired)
    assert _cp_states[KEY] == "STABLE"


def test_change_point_detects_mean_shift_once():
    """30 정상 + 30 shift(+10) → 60번째 call 에서 CHANGE_POINT 1회 발화."""
    fired = []
    for i in range(30):
        is_cp, _ = detect_change_point(KEY, 99.5 + (i % 2))  # mean≈100
        fired.append(is_cp)
    for i in range(30):
        is_cp, _ = detect_change_point(KEY, 109.5 + (i % 2))  # mean≈110, +10 shift
        fired.append(is_cp)
    assert fired.count(True) == 1
    assert fired[-1] is True  # 60번째 call 에서 fire
    assert _cp_states[KEY] == "SHIFT"


def test_change_point_no_duplicate_fire_immediately_after():
    """초기 STABLE→SHIFT 발화 직후 5 call 동안 중복 fire 0 (상태 머신 보호).

    이 짧은 구간은 prev 가 아직 normal 다수라 is_change=True 지속 → state=SHIFT.
    SHIFT 상태에서는 fire 안 함 (StateMachine 의 중복 발화 가드).
    """
    for i in range(30):
        detect_change_point(KEY, 99.5 + (i % 2))
    for i in range(30):
        detect_change_point(KEY, 109.5 + (i % 2))
    assert _cp_states[KEY] == "SHIFT"
    extra_fired = []
    for i in range(5):
        is_cp, meta = detect_change_point(KEY, 109.5 + (i % 2))
        extra_fired.append(is_cp)
        assert meta["state"] == "SHIFT"
    assert all(not f for f in extra_fired)


def test_change_point_eventually_recovers_to_stable():
    """SHIFT 후 정상 시계열 충분히 길게 → 최종 state=STABLE (BACK_TO_STABLE).

    Note: 윈도우가 normal/shift 혼재 구간을 지나는 동안 state 가 일시적으로
    STABLE↔SHIFT 사이클을 돌 수 있음 (sub-window 통계 흔들림). 본 테스트는
    "최종적으로 안정 상태로 돌아온다" 만 보장. 사이클 0 보장은 의도 X.
    """
    for i in range(30):
        detect_change_point(KEY, 99.5 + (i % 2))
    for i in range(30):
        detect_change_point(KEY, 109.5 + (i % 2))
    assert _cp_states[KEY] == "SHIFT"
    # 윈도우 2개 길이 (120) 만큼 정상 시계열 → 안정 상태 확정
    for i in range(120):
        detect_change_point(KEY, 99.5 + (i % 2))
    assert _cp_states[KEY] == "STABLE"


def test_change_point_detects_std_ratio_change():
    """평균 유지 + 분산 6배 증가 → std_ratio trigger 로 CHANGE_POINT 발화."""
    # 30 low-noise (std≈0.5, mean=100)
    for i in range(30):
        detect_change_point(KEY, 99.5 + (i % 2))
    # 30 high-noise (std≈3, mean=100 동일) — mean_shift≈0, std_ratio≈6
    fired = []
    fire_meta: dict = {}
    for i in range(30):
        is_cp, meta = detect_change_point(KEY, 97.0 + (i % 2) * 6.0)
        fired.append(is_cp)
        if is_cp:
            fire_meta = meta
    assert fired.count(True) == 1
    assert _cp_states[KEY] == "SHIFT"
    # std_ratio 가 trigger — mean_shift 는 ~0
    assert fire_meta["std_ratio"] >= 2.0
    assert fire_meta["mean_shift"] < 3.0
