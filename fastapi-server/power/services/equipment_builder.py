# power/services/equipment_builder.py — 전력 채널 16개 equipment 조립
#
# 데이터 흐름:
#   IN  : websocket.state.power_latest (watt/current/voltage/onoff 채널별 dict)
#         + channel_meta_cache (DRF PowerDevice.channel_meta 의 정격·라벨)
#   OUT : equipment list[dict] (채널별 측정값 + 3축 risk) + total_kw float
#         broadcast_loop 가 WebSocket 으로 브라우저에 송신.
#
# 단일 진실 공급원: 본 모듈의 risk 산출은 **대시보드 색상 표시용**.
#   실제 알람 트리거는 DRF apps.monitoring.services.power_alarm 이 담당.
from core.power_thresholds import POWER_THRESHOLDS
from power.services.channel_meta_cache import get_channel_entry
from websocket.state import power_latest

# 정격 % 임계 — DRF facilities.Threshold "power_facility_default" 와 단일 동기.
_PCT_THRESHOLDS = {
    "watt": {"warning": 80, "danger": 100, "bidirectional": False},
    "current": {"warning": 80, "danger": 100, "bidirectional": False},
    "voltage": {
        "warning_low": 95,
        "warning_high": 105,
        "danger_low": 90,
        "danger_high": 110,
        "bidirectional": True,
    },
}

_AXIS_BY_KEY = {"watt": "rated_w", "current": "rated_a", "voltage": "rated_v"}


def _eval_axis_pct(value: float | None, rated, axis: str) -> str:
    """정격 % 환산 후 임계치 비교. DRF threshold_service 와 동일 시맨틱 (>=).

    정격 미수신 또는 0 일 때 normal 로 fallback (표시 안전).
    voltage 는 bidirectional — 저전압·고전압 모두 위험.
    """
    if value is None or rated is None:
        return "normal"
    try:
        rated_f = float(rated)
    except (TypeError, ValueError):
        return "normal"
    if rated_f == 0:
        return "normal"
    pct = value / rated_f * 100
    cfg = _PCT_THRESHOLDS[axis]
    if cfg["bidirectional"]:
        if pct <= cfg["danger_low"] or pct >= cfg["danger_high"]:
            return "danger"
        if pct <= cfg["warning_low"] or pct >= cfg["warning_high"]:
            return "warning"
        return "normal"
    if pct >= cfg["danger"]:
        return "danger"
    if pct >= cfg["warning"]:
        return "warning"
    return "normal"


def _max_risk(levels: list[str]) -> str:
    order = {"normal": 0, "warning": 1, "danger": 2}
    return max(levels, key=lambda lv: order.get(lv, 0))


def _legacy_watt_risk(watt: float | None) -> str:
    """channel_meta 미수신 시 watt 절대값 fallback (POWER_THRESHOLDS)."""
    if watt is None:
        return "normal"
    if watt > POWER_THRESHOLDS["danger"]:
        return "danger"
    if watt > POWER_THRESHOLDS["caution"]:
        return "warning"
    return "normal"


def build_equipment() -> tuple[list[dict], float]:
    """power_latest 공유 상태를 읽어 16채널 equipment 목록과 총 전력(kW)을 조립한다.

    1. watt/current/voltage 가 모두 None → 통신 불능 (comm_failure, risk=normal)
    2. 채널별 정격 조회 → 3축 (watt/current/voltage) 의 정격 % risk 산출
    3. 정격 미입력 채널의 watt 만 POWER_THRESHOLDS 절대값으로 fallback
    4. risk_level = max(3축 risk)

    Returns:
        (equipment list, total_kw) — broadcast_loop 가 WebSocket 으로 송신.
    """
    if not any(
        [power_latest["watt"], power_latest["current"], power_latest["voltage"]]
    ):
        return [], 0.0

    equipment = []
    total_w = 0.0

    for ch in range(1, 17):
        watt = power_latest["watt"].get(ch)
        voltage = power_latest["voltage"].get(ch)
        current = power_latest["current"].get(ch)
        onoff = power_latest["onoff"].get(str(ch))

        is_comm = watt is None and voltage is None and current is None
        sensor_status = "comm_failure" if is_comm else "active"

        entry = get_channel_entry(None, ch)
        label = entry.get("name") or f"CH{ch}"

        if is_comm:
            power_risk = current_risk = voltage_risk = risk_level = "normal"
        else:
            rated_w = entry.get("rated_w")
            if rated_w is not None:
                power_risk = _eval_axis_pct(watt, rated_w, "watt")
            else:
                power_risk = _legacy_watt_risk(watt)
            current_risk = _eval_axis_pct(current, entry.get("rated_a"), "current")
            voltage_risk = _eval_axis_pct(voltage, entry.get("rated_v"), "voltage")
            risk_level = _max_risk([power_risk, current_risk, voltage_risk])
            if watt is not None:
                total_w += watt

        equipment.append(
            {
                "name": label,
                "watt": watt,
                "voltage": voltage,
                "current": current,
                "onoff": onoff,
                "sensor_status": sensor_status,
                "risk_level": risk_level,
                "power_risk": power_risk,
                "current_risk": current_risk,
                "voltage_risk": voltage_risk,
            }
        )

    return equipment, round(total_w / 1000, 3)
