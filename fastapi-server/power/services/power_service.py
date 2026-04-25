# power/services/power_service.py — 전력 공유 상태 갱신 + DRF 전송 헬퍼
from datetime import datetime, timezone

import httpx

from core.config import settings
from websocket.state import power_latest

DRF_POWER_EVENT_URL = f"{settings.DRF_BASE_URL}/api/monitoring/power/event/"
DRF_POWER_DATA_URL = f"{settings.DRF_BASE_URL}/api/monitoring/power/data/"

# 채널 → 설비명 매핑 (운영 시 DRF PowerDevice.channel_meta 조회로 교체)
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
    return datetime.now(timezone.utc).isoformat()


def auth_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if settings.DRF_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {settings.DRF_SERVICE_TOKEN}"
    return headers


async def post_to_drf(url: str, payload: dict) -> None:
    """DRF 비동기 전송. BackgroundTask용 — 실패해도 WS 흐름을 막지 않는다."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(url, json=payload, headers=auth_headers())
            if res.status_code not in (200, 201):
                print(f"[DRF] 저장 실패 {res.status_code}: {res.text[:80]}")
    except httpx.TimeoutException:
        print("[DRF] 응답 타임아웃")
    except Exception as e:
        print(f"[DRF] 전송 오류: {e}")


def to_channel_list(channel_values: dict) -> list[dict]:
    """채널값 dict → DRF channels 리스트 변환. None = 통신 불능."""
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
    """power_latest 공유 상태 갱신."""
    power_latest[data_type] = values
    power_latest["updated_at"] = measured_at


def build_equipment() -> tuple[list[dict], float]:
    """
    power_latest(채널 기반) → equipment[] + total_kw 반환.
    데이터 미수신 시 빈 리스트 반환 (브로드캐스트에서 스켈레톤 처리).
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
                "danger" if watt > 4000 else "warning" if watt > 2500 else "normal"
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
