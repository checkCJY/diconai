# dummies/_state_machine.py — 더미 시뮬레이터용 채널 상태 머신
#
# IF 학습 데이터에 시계열 자기상관을 부여하기 위한 4상태 FSM.
#
#   NORMAL ──(시나리오 진입)──> RAMP_UP ──(N틱 점진 상승)──> SCENARIO_HOLD
#                                                              │
#                                                (HOLD 만료) ──> RAMP_DOWN ──> NORMAL
#
# - 채널별로 독립된 ChannelState 인스턴스를 갖고, 각 틱마다 step() 호출
# - RAMP_UP/DOWN 구간은 선형 보간 가중치(0→1, 1→0)를 반환 → power_dummy 가
#   normal 값과 scenario 값을 가중 평균해 부드러운 전이 생성
# - HOLD 구간은 scenario 값 100% 사용
# - NORMAL 구간은 normal 값 100% 사용
#
# 가스 plan 에서도 동일 헬퍼를 재사용할 수 있도록 도메인 비종속 설계.

from __future__ import annotations

import random
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 상태 정의
# ---------------------------------------------------------------------------


NORMAL = "normal"
RAMP_UP = "ramp_up"
HOLD = "hold"
RAMP_DOWN = "ramp_down"


@dataclass
class ChannelState:
    """채널 1개의 시나리오 진행 상태."""

    state: str = NORMAL
    scenario: str | None = None
    ticks_in_state: int = 0
    ramp_up_ticks: int = 5
    hold_ticks: int = 10
    ramp_down_ticks: int = 10


@dataclass
class StateOutput:
    """step() 결과 — 채널의 현재 출력 가중치와 라벨."""

    scenario_weight: float  # 0.0 = normal 100%, 1.0 = scenario 100%
    is_anomaly: bool
    anomaly_type: str | None


# ---------------------------------------------------------------------------
# 핵심 API
# ---------------------------------------------------------------------------


def enter_scenario(
    cs: ChannelState,
    scenario: str,
    ramp_up_ticks: int = 5,
    hold_ticks: int = 10,
    ramp_down_ticks: int = 10,
) -> None:
    """NORMAL 상태인 채널을 시나리오로 진입시킨다. 이미 진행 중이면 무시.

    각 ticks 인자는 1 미만이면 1로 보정 — 0틱 RAMP 구간이 발생해 ZeroDivision 을 막는다.
    """
    if cs.state != NORMAL:
        return
    cs.state = RAMP_UP
    cs.scenario = scenario
    cs.ticks_in_state = 0
    cs.ramp_up_ticks = max(1, ramp_up_ticks)
    cs.hold_ticks = max(1, hold_ticks)
    cs.ramp_down_ticks = max(1, ramp_down_ticks)


def step(cs: ChannelState) -> StateOutput:
    """1틱 진행 후 현재 상태 출력을 반환한다.

    반환 `scenario_weight`: NORMAL=0.0, RAMP_UP=ticks/ramp_up_ticks (0→1),
    HOLD=1.0, RAMP_DOWN=remaining/ramp_down_ticks (1→0).
    HOLD 만료 시 자동 RAMP_DOWN 으로 전이, RAMP_DOWN 만료 시 NORMAL 로 복귀.
    """
    cs.ticks_in_state += 1

    if cs.state == NORMAL:
        return StateOutput(scenario_weight=0.0, is_anomaly=False, anomaly_type=None)

    if cs.state == RAMP_UP:
        weight = min(1.0, cs.ticks_in_state / cs.ramp_up_ticks)
        if cs.ticks_in_state >= cs.ramp_up_ticks:
            cs.state = HOLD
            cs.ticks_in_state = 0
        # RAMP_UP 동안은 이미 이상 시나리오 라벨로 처리 (IF 학습 데이터에서 전이 구간도 anomaly)
        return StateOutput(
            scenario_weight=weight, is_anomaly=True, anomaly_type=cs.scenario
        )

    if cs.state == HOLD:
        if cs.ticks_in_state >= cs.hold_ticks:
            cs.state = RAMP_DOWN
            cs.ticks_in_state = 0
        return StateOutput(
            scenario_weight=1.0, is_anomaly=True, anomaly_type=cs.scenario
        )

    # RAMP_DOWN
    remaining = max(0, cs.ramp_down_ticks - cs.ticks_in_state)
    weight = remaining / cs.ramp_down_ticks
    if cs.ticks_in_state >= cs.ramp_down_ticks:
        cs.state = NORMAL
        cs.scenario = None
        cs.ticks_in_state = 0
        return StateOutput(scenario_weight=0.0, is_anomaly=False, anomaly_type=None)
    return StateOutput(
        scenario_weight=weight, is_anomaly=True, anomaly_type=cs.scenario
    )


def maybe_trigger(
    cs: ChannelState,
    probability: float,
    scenarios: list[str],
    weights: list[int],
    hold_ticks_by_scenario: dict[str, int],
    ramp_up_ticks: int = 5,
    ramp_down_ticks: int = 10,
) -> None:
    """NORMAL 상태일 때 probability 로 시나리오를 무작위 진입시킨다.

    scenarios·weights 는 random.choices() 가중치 선택용.
    """
    if cs.state != NORMAL:
        return
    if random.random() >= probability:
        return
    picked = random.choices(scenarios, weights=weights, k=1)[0]
    enter_scenario(
        cs,
        scenario=picked,
        ramp_up_ticks=ramp_up_ticks,
        hold_ticks=hold_ticks_by_scenario.get(picked, 10),
        ramp_down_ticks=ramp_down_ticks,
    )


def mix(normal_value: float, scenario_value: float, weight: float) -> float:
    """RAMP 구간 선형 보간. weight=0.0 → normal, 1.0 → scenario."""
    return normal_value * (1.0 - weight) + scenario_value * weight
