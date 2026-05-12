# power/services/power_service.py — 전력 데이터 처리 서비스
#
# 전력 센서 수신 데이터와 관련된 비즈니스 로직을 담당한다.
#   - DRF 비동기 전송 (BackgroundTask용 fire-and-forget 패턴)
#   - power_latest 공유 상태 갱신
#   - 채널 데이터를 equipment[] 형태로 조립해 WebSocket 브로드캐스트에 제공
#   - 채널 라벨·정격은 channel_meta_cache(DRF PowerDevice.channel_meta)에서 조회
import logging
from datetime import datetime, timezone

from core.power_thresholds import POWER_THRESHOLDS
from power.services.channel_meta_cache import get_channel_entry
from services.drf_client import post_to_drf
from websocket.state import power_latest

logger = logging.getLogger(__name__)

DRF_POWER_EVENT_PATH = "/api/monitoring/power/event/"
DRF_POWER_DATA_PATH = "/api/monitoring/power/data/"

# 페이로드 표시용 정격 % 임계치 (DRF facilities.Threshold "power_facility_default"와 동일)
# 실제 알람 트리거는 DRF가 단일 진실 공급원. 본 모듈은 대시보드 색상 표시만 담당.
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


def now_utc_iso() -> str:
    """현재 UTC 시각을 ISO 8601 문자열로 반환한다."""
    return datetime.now(timezone.utc).isoformat()


async def post_power_to_drf(path: str, payload: dict) -> None:
    """전력 데이터를 DRF에 비동기 fire-and-forget 전송.

    BackgroundTask에서 실행되므로 실패해도 WebSocket 흐름을 블로킹하지 않는다.
    실패는 services.drf_client가 logger.warning/error로 기록한다.
    """
    await post_to_drf(path, payload, raise_on_error=False, log_category="power_service")


def to_channel_list(channel_values: dict) -> list[dict]:
    """
    채널별 측정값 딕셔너리를 DRF PowerData 저장 형식(리스트)으로 변환한다.
    값이 None인 채널은 통신 불능(comm_failure) 상태로 표시한다.
    """
    return [
        {
            "channel": ch,
            "value": val,
            "sensor_status": "comm_failure" if val is None else "active",
            "risk_level": "normal",
        }
        for ch, val in channel_values.items()
    ]


def update_power_state(data_type: str, values: dict, measured_at: str) -> None:
    """
    power_latest 공유 상태를 갱신한다.
    갱신된 값은 다음 WebSocket 틱에서 build_equipment()를 통해 브라우저로 전달된다.
    """
    power_latest[data_type] = values
    power_latest["updated_at"] = measured_at


def _eval_axis_pct(value: float | None, rated, axis: str) -> str:
    """정격 % 환산 후 임계치 비교. 표시용 — DRF threshold_service와 동일 시맨틱(>=)."""
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
    """
    power_latest 공유 상태를 읽어 equipment 목록과 총 전력(kW)을 조립한다.

    [축별 risk 표시]
    채널 정격(channel_meta[ch][rated_*])을 사용해 W·A·V 각 축의 % 위험도를 산출.
    정격 미입력 시 power_risk만 POWER_THRESHOLDS 절대값으로 fallback.
    종합 risk_level = max(power_risk, current_risk, voltage_risk).

    [단일 진실 공급원]
    본 함수의 risk 산출은 대시보드 색상 표시용. 실제 알람 트리거는 DRF의
    apps.monitoring.services.power_alarm.trigger_power_alarms()가 담당.
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
