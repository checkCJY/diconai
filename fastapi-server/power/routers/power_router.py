# power/routers/power_router.py — 전력 센서 HTTP 수신 엔드포인트
#
# 전력 센서 장비로부터 4종의 측정 데이터를 수신하는 라우터.
# 같은 device_id에서 측정 타입별로 분리된 요청이 들어온다(프로토콜 규정).
#   POST /api/power/onoff    : 16채널 ON/OFF 상태 스냅샷  → DRF PowerEvent
#   POST /api/power/current  : 16채널 전류(A)             → DRF PowerData
#   POST /api/power/voltage  : 16채널 전압(V)             → DRF PowerData
#   POST /api/power/watt     : 16채널 전력(W)             → DRF PowerData
#
# 모든 엔드포인트의 처리 흐름:
#   1. Pydantic 스키마로 수신 데이터 검증 후 채널 딕셔너리로 변환
#   2. power_latest 공유 상태 즉시 갱신 → WebSocket 브로드캐스트에 즉시 반영
#   3. DRF 저장은 BackgroundTask로 비동기 처리 → 응답을 블로킹하지 않음
from fastapi import APIRouter, BackgroundTasks

from power.schemas.power import (
    PowerCurrentPayload,
    PowerOnOffPayload,
    PowerVoltagePayload,
    PowerWattPayload,
)
from power.services.power_service import (
    DRF_POWER_DATA_PATH,
    DRF_POWER_EVENT_PATH,
    now_utc_iso,
    post_power_to_drf,
    to_channel_list,
    update_power_state,
)

router = APIRouter(prefix="/api/power", tags=["power"])


@router.post("/onoff", status_code=201)
async def recv_onoff(payload: PowerOnOffPayload, bg: BackgroundTasks):
    """ON/OFF 스냅샷을 수신해 공유 상태를 갱신하고 DRF PowerEvent에 비동기 저장한다."""
    snapshot = payload.to_snapshot()
    measured_at = now_utc_iso()
    update_power_state("onoff", snapshot, measured_at)
    bg.add_task(
        post_power_to_drf,
        DRF_POWER_EVENT_PATH,
        {
            "device_id": payload.device_id,
            "measured_at": measured_at,
            "snapshot": snapshot,
        },
    )
    return {"status": "ok", "updated": "onoff"}


@router.post("/current", status_code=201)
async def recv_current(payload: PowerCurrentPayload, bg: BackgroundTasks):
    """전류 측정값을 수신해 공유 상태를 갱신하고 DRF PowerData에 비동기 저장한다."""
    channel_values = payload.to_channel_values()
    measured_at = now_utc_iso()
    update_power_state("current", channel_values, measured_at)
    bg.add_task(
        post_power_to_drf,
        DRF_POWER_DATA_PATH,
        {
            "device_id": payload.device_id,
            "measured_at": measured_at,
            "data_type": "current",
            "channels": to_channel_list(channel_values),
        },
    )
    return {"status": "ok", "updated": "current"}


@router.post("/voltage", status_code=201)
async def recv_voltage(payload: PowerVoltagePayload, bg: BackgroundTasks):
    """전압 측정값을 수신해 공유 상태를 갱신하고 DRF PowerData에 비동기 저장한다."""
    channel_values = payload.to_channel_values()
    measured_at = now_utc_iso()
    update_power_state("voltage", channel_values, measured_at)
    bg.add_task(
        post_power_to_drf,
        DRF_POWER_DATA_PATH,
        {
            "device_id": payload.device_id,
            "measured_at": measured_at,
            "data_type": "voltage",
            "channels": to_channel_list(channel_values),
        },
    )
    return {"status": "ok", "updated": "voltage"}


@router.post("/watt", status_code=201)
async def recv_watt(payload: PowerWattPayload, bg: BackgroundTasks):
    """전력(W) 측정값을 수신해 공유 상태를 갱신하고 DRF PowerData에 비동기 저장한다."""
    channel_values = payload.to_channel_values()
    measured_at = now_utc_iso()
    update_power_state("watt", channel_values, measured_at)
    bg.add_task(
        post_power_to_drf,
        DRF_POWER_DATA_PATH,
        {
            "device_id": payload.device_id,
            "measured_at": measured_at,
            "data_type": "watt",
            "channels": to_channel_list(channel_values),
        },
    )
    return {"status": "ok", "updated": "watt"}
