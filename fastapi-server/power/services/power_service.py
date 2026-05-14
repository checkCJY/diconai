# power/services/power_service.py — 전력 데이터 처리 서비스
#
# 전력 센서 수신 데이터와 관련된 비즈니스 로직을 담당한다.
#   - DRF 비동기 전송 (BackgroundTask용 fire-and-forget 패턴)
#   - power_latest 공유 상태 갱신
#   - 채널 데이터를 equipment[] 형태로 조립해 WebSocket 브로드캐스트에 제공
#   - 채널 라벨·정격은 channel_meta_cache(DRF PowerDevice.channel_meta)에서 조회
#   - [트랙 1 v2] IF 추론 + combine_risk + push_alarm (process_anomaly_inference)
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone

from ai.risk_combine import combine_risk
from ai.router import _build_feature_row, _get_or_load
from core.power_thresholds import POWER_THRESHOLDS
from power.services.channel_meta_cache import get_channel_entry
from power.services.threshold_eval import calculate_power_risk
from services.drf_client import post_to_drf
from websocket.services.alarm_queue import push_alarm
from websocket.state import power_latest

logger = logging.getLogger(__name__)

# IF 추론용 in-memory 윈도우 — (channel, data_type) 별 deque(maxlen=window).
# 가스 _co_window 패턴을 power 다채널·다측정으로 확장. fastapi 재시작 시 초기화 (무상태).
_INFERENCE_WINDOW = 30
_power_windows: dict[tuple[int, str], deque] = defaultdict(
    lambda: deque(maxlen=_INFERENCE_WINDOW)
)

# combined_risk → AlarmPayload.risk_level (RiskLevel) 매핑.
# CAUTION/PREDICT_WARN 둘 다 RiskLevel.WARNING 으로 (RiskLevel 3단계라 합칠 수밖에).
# UI 에서 더 풍부한 구분은 C8 에서 AlarmPayload 에 combined_risk 필드 추가 후 가능.
_COMBINED_TO_RISK_LEVEL = {
    "normal": "normal",
    "caution": "warning",
    "predict_warn": "warning",
    "danger": "danger",
}
_FIRE_LEVELS = {"caution", "predict_warn", "danger"}

# 본 sprint active 모델은 (device_1, ch1, watt) 한 채널만 학습됨.
# 다른 채널은 학습 분포 안 맞아 false positive ↑ → §3 multi-channel sprint 까지 비활성.
_INFERENCE_ENABLED_CHANNELS: set[tuple[int, str]] = {(1, "watt")}

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


DRF_ML_ANOMALY_RESULT_PATH = "/api/ml/anomaly-results/"


async def process_anomaly_inference(
    device_id: str | None,
    channel_values: dict,
    data_type: str,
    measured_at: str,
) -> None:
    """[트랙 1 v2] IF 추론 + combine_risk + push_alarm + DRF MLAnomalyResult forward.

    ch1·watt 등 _INFERENCE_ENABLED_CHANNELS 에 포함된 (channel, data_type) 만 추론.
    윈도우 누적 < _INFERENCE_WINDOW 면 skip. push_alarm 은 발화 levels 일 때만,
    MLAnomalyResult forward 는 추론 매번 (운영 추적용). 모든 외부 호출 silent fail —
    DRF 저장 흐름과 fastapi 응답 시간에 영향 없음.
    """
    for channel, value in channel_values.items():
        if (channel, data_type) not in _INFERENCE_ENABLED_CHANNELS:
            continue
        if value is None:
            continue
        win = _power_windows[(channel, data_type)]
        win.append(float(value))
        if len(win) < _INFERENCE_WINDOW:
            continue

        try:
            entry = await _get_or_load("power")
            row = _build_feature_row(list(win), entry.window)
            score = float(entry.model.decision_function(row)[0])
            pred_int = int(entry.model.predict(row)[0])
            prediction = "anomaly" if pred_int == -1 else "normal"

            threshold_risk = calculate_power_risk(value, data_type, device_id, channel)
            combined = combine_risk(threshold_risk, prediction)
            features = {
                "value": float(row[0, 0]),
                "roll_mean": float(row[0, 1]),
                "roll_std": float(row[0, 2]),
                "diff": float(row[0, 3]),
            }
            sensor_identifier = f"power:device_{device_id}:ch{channel}:{data_type}"

            # MLAnomalyResult 운영 추적용 forward — 발화 여부 무관, 추론 매번 저장.
            # silent fail (raise_on_error=False) — DRF 다운 시 알람 push 흐름 영향 X.
            await post_to_drf(
                DRF_ML_ANOMALY_RESULT_PATH,
                {
                    "ml_model": None,  # SET_NULL 허용. version 추적은 snapshot 으로
                    "model_version_snapshot": entry.version,
                    "sensor_type": "power",
                    "sensor_identifier": sensor_identifier,
                    "measured_at": measured_at,
                    "anomaly_score": score,
                    "prediction": prediction,
                    "risk_classified": combined,
                    "feature_snapshot_json": features,
                },
                raise_on_error=False,
                log_category="power_anomaly_forward",
            )

            if combined not in _FIRE_LEVELS:
                continue

            entry_meta = get_channel_entry(device_id, channel)
            label = entry_meta.get("name") or f"CH{channel}"
            summary = (
                f"[AI 이상 패턴] {label} {data_type}={value} "
                f"(IF score {score:.4f}, combined={combined})"
            )
            await push_alarm(
                {
                    "alarm_type": "power_anomaly_ai",
                    "risk_level": _COMBINED_TO_RISK_LEVEL[combined],
                    "source_label": label,
                    "summary": summary,
                    "is_new_event": True,
                    "measured_value": value,
                    # AnomalyMeta nested — UI 가 PREDICT_WARN/CAUTION 차별화 표시 가능
                    "anomaly_meta": {
                        "combined_risk": combined,
                        "anomaly_score": score,
                        "device_id": device_id,
                        "channel": channel,
                        "data_type": data_type,
                    },
                }
            )
            logger.info(
                "[anomaly_inference] device=%s ch=%s %s value=%s "
                "threshold=%s pred=%s combined=%s score=%.4f",
                device_id,
                channel,
                data_type,
                value,
                threshold_risk,
                prediction,
                combined,
                score,
            )
        except Exception as exc:
            logger.warning(
                "[anomaly_inference] failed device=%s ch=%s %s: %s",
                device_id,
                channel,
                data_type,
                exc,
            )


def to_channel_list(
    channel_values: dict, anomaly_map: dict | None = None
) -> list[dict]:
    """
    채널별 측정값 딕셔너리를 DRF PowerData 저장 형식(리스트)으로 변환한다.
    값이 None인 채널은 통신 불능(comm_failure) 상태로 표시한다.

    anomaly_map : {channel:int → anomaly_type:str} — 더미 시뮬레이터에서만 채워짐.
                  해당 채널은 is_anomaly=True 로 저장된다.
    """
    anomaly_map = anomaly_map or {}
    return [
        {
            "channel": ch,
            "value": val,
            "sensor_status": "comm_failure" if val is None else "active",
            "risk_level": "normal",
            "is_anomaly": ch in anomaly_map,
            "anomaly_type": anomaly_map.get(ch),
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
