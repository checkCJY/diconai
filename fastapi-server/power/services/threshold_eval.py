"""
threshold_eval — fastapi 측 power threshold 평가 (트랙 1 v2)

[배경]
DRF evaluate_power_risk / _current / _voltage 의 정격 % 환산 룰을 fastapi 에 복제.
가스 측 calculate_individual_risks (core/gas_thresholds.py) 패턴 차용.
fastapi 안에서 IF 추론 + threshold 평가를 같은 process 에서 수행 후 combine_risk
호출 → push_alarm. DRF 호출 없이 in-memory 만으로 알람 판단.

[임계 — DRF Threshold 'power_facility_default' 시드와 일치]
- watt:    warning_max=80%, danger_max=100%   (단방향, >=)
- current: warning_max=80%, danger_max=100%   (단방향, >=)
- voltage: warning [95%, 105%], danger [90%, 110%]  (양방향)

DRF Threshold 운영자 변경 시 본 모듈 hardcode 동기 수정 필요 (가스 측과 동일 한계).
"""

from __future__ import annotations

from power.services.channel_meta_cache import get_channel_entry
from power.services.threshold_sync import get_threshold_meta

# T4 D2 — fastapi data_type → DRF Threshold.measurement_item 매핑.
_DRF_ITEM_BY_DATA_TYPE = {
    "watt": "power_w",
    "current": "current",
    "voltage": "voltage",
}
_RATED_KEY_BY_DATA_TYPE = {
    "watt": "rated_w",
    "current": "rated_a",
    "voltage": "rated_v",
}

# 단방향 (W, A)
WATT_WARNING_PCT = 80.0
WATT_DANGER_PCT = 100.0
CURRENT_WARNING_PCT = 80.0
CURRENT_DANGER_PCT = 100.0

# 양방향 (V)
VOLTAGE_WARNING_MIN_PCT = 95.0
VOLTAGE_WARNING_MAX_PCT = 105.0
VOLTAGE_DANGER_MIN_PCT = 90.0
VOLTAGE_DANGER_MAX_PCT = 110.0


def _evaluate_unidirectional(
    value_pct: float, warning_pct: float, danger_pct: float
) -> str:
    """단방향 (>=) — value_pct >= danger_pct → DANGER, >= warning_pct → WARNING."""
    if value_pct >= danger_pct:
        return "danger"
    if value_pct >= warning_pct:
        return "warning"
    return "normal"


def _evaluate_bidirectional(
    value_pct: float,
    warning_min: float,
    warning_max: float,
    danger_min: float,
    danger_max: float,
) -> str:
    """양방향 — 너무 낮거나 너무 높으면 위험 (전압)."""
    if value_pct <= danger_min or value_pct >= danger_max:
        return "danger"
    if value_pct <= warning_min or value_pct >= warning_max:
        return "warning"
    return "normal"


def calculate_power_risk(
    value: float | None,
    data_type: str,
    device_id: str | None,
    channel: int,
) -> str:
    """value (W/A/V) → 'normal' | 'warning' | 'danger'.

    Args:
        value: 측정값 (None 이면 normal)
        data_type: 'watt' | 'current' | 'voltage'
        device_id: PowerDevice.device_id (channel_meta_cache lookup 키)
        channel: 채널 번호 (1~16)

    정격 entry 가 없거나 0 이면 fail-safe 로 'normal' 반환.
    """
    if value is None:
        return "normal"
    entry = get_channel_entry(device_id, channel)
    if data_type == "watt":
        rated = entry.get("rated_w")
        if not rated:
            return "normal"
        pct = float(value) / float(rated) * 100.0
        return _evaluate_unidirectional(pct, WATT_WARNING_PCT, WATT_DANGER_PCT)
    if data_type == "current":
        rated = entry.get("rated_a")
        if not rated:
            return "normal"
        pct = float(value) / float(rated) * 100.0
        return _evaluate_unidirectional(pct, CURRENT_WARNING_PCT, CURRENT_DANGER_PCT)
    if data_type == "voltage":
        rated = entry.get("rated_v")
        if not rated:
            return "normal"
        pct = float(value) / float(rated) * 100.0
        return _evaluate_bidirectional(
            pct,
            VOLTAGE_WARNING_MIN_PCT,
            VOLTAGE_WARNING_MAX_PCT,
            VOLTAGE_DANGER_MIN_PCT,
            VOLTAGE_DANGER_MAX_PCT,
        )
    raise ValueError(f"Unknown data_type: {data_type!r}")


def evaluate_static_risk_from_cache(
    value: float | None,
    data_type: str,
    device_id: str | None,
    channel: int,
) -> str:
    """T4 D2 — DRF threshold-meta sync 캐시 기반 정적 평가.

    `calculate_power_risk` 와 같은 % 환산 로직이지만, 임계치 출처가 DRF sync 캐시
    (D1b `threshold_sync.get_threshold_meta`). decide_alarm 매트릭스 (T4 plan §5)
    의 "정적 fired/not fired" 입력 단일 진실 공급원.

    `calculate_power_risk` 는 hardcoded 상수 (80%/100%) — combine_risk_5axis 의
    축 입력. 본 함수는 별개 — admin 임계치 수정 반영. 두 함수의 결과가 다를 수
    있음 (5분 sync lag 동안 / admin 이 80% 외 값으로 수정 시) — plan §10 위험.

    fail-safe — 캐시 미존재 / 정격 미지정 / 임계치 None / data_type 미인식 →
    모두 'normal' 반환. AI 정상 + 정적 정상 = 알람 없음 (안전 측 보수적 분기).
    """
    if value is None:
        return "normal"
    item = _DRF_ITEM_BY_DATA_TYPE.get(data_type)
    if item is None:
        return "normal"
    meta = get_threshold_meta(item)
    if not meta:
        return "normal"
    entry = get_channel_entry(device_id, channel)
    rated = entry.get(_RATED_KEY_BY_DATA_TYPE[data_type])
    if not rated:
        return "normal"
    pct = float(value) / float(rated) * 100.0
    if data_type == "voltage":
        # 양방향 — 4 임계 중 하나라도 None 이면 +/- inf 로 fail-safe (그 방향 fire 안 됨).
        return _evaluate_bidirectional(
            pct,
            meta.get("warning_min")
            if meta.get("warning_min") is not None
            else float("-inf"),
            meta.get("warning_max")
            if meta.get("warning_max") is not None
            else float("inf"),
            meta.get("danger_min")
            if meta.get("danger_min") is not None
            else float("-inf"),
            meta.get("danger_max")
            if meta.get("danger_max") is not None
            else float("inf"),
        )
    # 단방향 (watt/current) — warning_max/danger_max 만 사용.
    warning_max = meta.get("warning_max")
    danger_max = meta.get("danger_max")
    if warning_max is None or danger_max is None:
        return "normal"
    return _evaluate_unidirectional(pct, float(warning_max), float(danger_max))
