"""
추론 측 sensor data quality guard — IF 학습 데이터에 통신/센서 오류가
흡수되는 것 방지.

ARIMA Un-격하 plan §W0 (skill/plan/power-ai-un-downgrade-phase2-apply.md §3)
의 일환. `process_anomaly_inference` 진입부에서 quality 를 검사한 뒤
부적합 값은 윈도우 적재·추론을 skip + 사유 라벨을 로그에 남긴다.

본 모듈은 추론 측 전용이며, raw 데이터 저장 흐름 (to_channel_list → DRF) 의
sensor_status 라벨링과는 분리되어 있다. raw 측은 현재 None=comm_failure 만
구분 — overflow/stuck 같은 추가 사유가 raw 저장에도 필요해질 경우 별도 작업.
"""

from __future__ import annotations

from collections import deque

from core.power_thresholds import UPPER_BOUND_BY_TYPE


def classify_sensor_status(value: float | None, data_type: str) -> str | None:
    """추론 가능한 값인지 판정 + 이상 시 라벨 반환.

    Parameters
    ----------
    value
        센서 측정값. None 또는 -1 (펌웨어 통신 단절 sentinel) 도 허용.
    data_type
        "watt" / "current" / "voltage" 중 하나. UPPER_BOUND_BY_TYPE 매핑에 사용.

    Returns
    -------
    None
        추론 진행 가능 (정상 값).
    "comm_failure"
        value 가 None 또는 -1 — 통신 단절 신호. IF 윈도우 적재 skip.
    "sensor_fault_overflow"
        value 가 UPPER_BOUND_BY_TYPE[data_type] 초과 — 펌웨어/센서 오버플로우.
    """
    if value is None:
        return "comm_failure"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "comm_failure"
    if v == -1:
        return "comm_failure"
    bound = UPPER_BOUND_BY_TYPE.get(data_type)
    if bound is not None and v > bound:
        return "sensor_fault_overflow"
    return None


def is_inference_stuck(history: deque) -> bool:
    """슬라이딩 윈도우가 가득 찼는데 모든 값이 동일하면 stuck (센서 고정 고장).

    예: 99999 가 30틱 연속 송신 (또는 동일 fault 값 반복) → 윈도우 분산 0 →
    IF 입력 분포 자체가 부적합 → 추론 skip.

    윈도우 미충족 (warmup 구간) 시에는 false (정상 추론 회피하지 않음).
    """
    if history.maxlen is None or len(history) < history.maxlen:
        return False
    first = history[0]
    return all(x == first for x in history)
