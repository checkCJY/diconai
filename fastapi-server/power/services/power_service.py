# power/services/power_service.py — 전력 데이터 처리 서비스
#
# 전력 센서 수신 데이터와 관련된 비즈니스 로직을 담당한다.
#   - DRF 비동기 전송 (BackgroundTask용 fire-and-forget 패턴)
#   - power_latest 공유 상태 갱신
#   - 채널 데이터를 equipment[] 형태로 조립해 WebSocket 브로드캐스트에 제공
import logging
from datetime import datetime, timezone

from core.power_thresholds import POWER_THRESHOLDS
from services.drf_client import post_to_drf
from websocket.state import power_latest

logger = logging.getLogger(__name__)

DRF_POWER_EVENT_PATH = "/api/monitoring/power/event/"
DRF_POWER_DATA_PATH = "/api/monitoring/power/data/"

# 채널 번호 → 설비명 매핑
# 운영 환경에서는 DRF PowerDevice.channel_meta 조회로 교체 예정
CHANNEL_TO_DEVICE: dict[int, str] = {
    1: "압연기",
    2: "송풍기",
    3: "집진기",
    4: "전자기 교반기",
    5: "냉각펌프",
    6: "유압장치",
    7: "컨베이어",
    8: "분쇄기",
    9: "CH9",
    10: "CH10",
    11: "CH11",
    12: "CH12",
    13: "CH13",
    14: "CH14",
    15: "CH15",
    16: "CH16",
}


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


def build_equipment() -> tuple[list[dict], float]:
    """
    power_latest 공유 상태를 읽어 equipment 목록과 총 전력(kW)을 조립한다.

    WebSocket 브로드캐스트 페이로드의 equipment[] 필드를 생성하는 데 사용된다.
    watt/current/voltage가 모두 비어있으면 데이터 미수신 상태로 간주해 빈 리스트를 반환한다.

    [risk_level 표시용 fallback — Phase 4 회귀 점검 fix]
    채널별 위험도: watt > POWER_THRESHOLDS["danger"] → danger, > POWER_THRESHOLDS["caution"]
    → warning, 그 외 → normal.

    본 risk_level은 표시용이며 실제 알람 판정 + DB 저장은 DRF의
    `apps.alerts.tasks.fire_power_*_task`가 담당 (Phase 4-b에서 DB Threshold 전환 완료).
    DRF GasData.save() 패턴과 일관: fastapi 측 risk는 페이로드 표시용, DRF가 단일 진실 공급원.
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

        if not is_comm and watt is not None:
            risk_level = (
                "danger"
                if watt > POWER_THRESHOLDS["danger"]
                else "warning"
                if watt > POWER_THRESHOLDS["caution"]
                else "normal"
            )
            total_w += watt
        else:
            risk_level = "normal"

        equipment.append(
            {
                "name": CHANNEL_TO_DEVICE.get(ch, f"CH{ch}"),
                "watt": watt,
                "voltage": voltage,
                "current": current,
                "onoff": onoff,
                "sensor_status": sensor_status,
                "risk_level": risk_level,
            }
        )

    return equipment, round(total_w / 1000, 3)
