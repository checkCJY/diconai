# power/routers/power_router.py — 전력 센서 HTTP 수신 엔드포인트
from fastapi import APIRouter, BackgroundTasks

from power.schemas.power import (
    PowerCurrentPayload,
    PowerOnOffPayload,
    PowerVoltagePayload,
    PowerWattPayload,
)
from power.services.power_service import (
    DRF_POWER_DATA_URL,
    DRF_POWER_EVENT_URL,
    now_utc_iso,
    post_to_drf,
    to_channel_list,
    update_power_state,
)

router = APIRouter(prefix="/api/power", tags=["power"])


@router.post("/onoff", status_code=201)
async def recv_onoff(payload: PowerOnOffPayload, bg: BackgroundTasks):
    snapshot = payload.to_snapshot()
    measured_at = now_utc_iso()
    update_power_state("onoff", snapshot, measured_at)
    bg.add_task(
        post_to_drf,
        DRF_POWER_EVENT_URL,
        {
            "device_id": payload.device_id,
            "measured_at": measured_at,
            "snapshot": snapshot,
        },
    )
    return {"status": "ok", "updated": "onoff"}


@router.post("/current", status_code=201)
async def recv_current(payload: PowerCurrentPayload, bg: BackgroundTasks):
    channel_values = payload.to_channel_values()
    measured_at = now_utc_iso()
    update_power_state("current", channel_values, measured_at)
    bg.add_task(
        post_to_drf,
        DRF_POWER_DATA_URL,
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
    channel_values = payload.to_channel_values()
    measured_at = now_utc_iso()
    update_power_state("voltage", channel_values, measured_at)
    bg.add_task(
        post_to_drf,
        DRF_POWER_DATA_URL,
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
    channel_values = payload.to_channel_values()
    measured_at = now_utc_iso()
    update_power_state("watt", channel_values, measured_at)
    bg.add_task(
        post_to_drf,
        DRF_POWER_DATA_URL,
        {
            "device_id": payload.device_id,
            "measured_at": measured_at,
            "data_type": "watt",
            "channels": to_channel_list(channel_values),
        },
    )
    return {"status": "ok", "updated": "watt"}
