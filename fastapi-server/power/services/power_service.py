# power/services/power_service.py — 전력 데이터 처리 서비스
#
# 전력 센서 수신 데이터와 관련된 비즈니스 로직을 담당한다.
#   - DRF 비동기 전송 (BackgroundTask용 fire-and-forget 패턴)
#   - power_latest 공유 상태 갱신
#   - 채널 데이터를 equipment[] 형태로 조립해 WebSocket 브로드캐스트에 제공
from datetime import datetime, timezone

import httpx

from core.config import settings
from websocket.state import power_latest

DRF_POWER_EVENT_URL = f"{settings.DRF_BASE_URL}/api/monitoring/power/event/"
DRF_POWER_DATA_URL = f"{settings.DRF_BASE_URL}/api/monitoring/power/data/"

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


def auth_headers() -> dict:
    """DRF 요청용 헤더를 반환한다. 토큰이 설정된 경우 Bearer 인증 헤더를 포함한다."""
    headers = {"Content-Type": "application/json"}
    if settings.DRF_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {settings.DRF_SERVICE_TOKEN}"
    return headers


async def post_to_drf(url: str, payload: dict) -> None:
    """
    DRF에 데이터를 비동기로 전송한다.

    BackgroundTask에서 실행되므로 실패해도 WebSocket 흐름을 블로킹하지 않는다.
    오류 발생 시 print로 로그를 남기고 무시한다.
    """
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
    채널별 위험도: watt > 4000W → danger, > 2500W → warning, 그 외 → normal
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
