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
    PowerIngestResponse,
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


_COMMON_RESPONSES = {
    422: {"description": "페이로드 검증 실패"},
    502: {
        "description": "DRF 저장 실패 (BackgroundTask 비동기라 본 응답에는 영향 없음)"
    },
}


@router.post(
    "/onoff",
    response_model=PowerIngestResponse,
    status_code=201,
    summary="전력 16채널 ON/OFF 스냅샷 수신",
    description=(
        "각 채널의 통전 여부(0/255 → bool)를 수신해 공유 상태를 갱신하고 "
        "DRF `PowerEvent`에 비동기 저장한다. ON/OFF 변화는 이벤트성 데이터로 취급."
    ),
    responses=_COMMON_RESPONSES,
)
async def recv_onoff(payload: PowerOnOffPayload, bg: BackgroundTasks):
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


@router.post(
    "/current",
    response_model=PowerIngestResponse,
    status_code=201,
    summary="전력 16채널 전류(A) 수신",
    description="각 채널의 전류값을 수신. -1은 통신 불능 채널 — DB에 저장되지만 통계에서 제외 필요.",
    responses=_COMMON_RESPONSES,
)
async def recv_current(payload: PowerCurrentPayload, bg: BackgroundTasks):
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


@router.post(
    "/voltage",
    response_model=PowerIngestResponse,
    status_code=201,
    summary="전력 16채널 전압(V) 수신",
    description="각 채널의 전압값을 수신. -1은 통신 불능 채널.",
    responses=_COMMON_RESPONSES,
)
async def recv_voltage(payload: PowerVoltagePayload, bg: BackgroundTasks):
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


@router.post(
    "/watt",
    response_model=PowerIngestResponse,
    status_code=201,
    summary="전력 16채널 전력(W) 수신",
    description=(
        "각 채널의 전력값을 수신. 임계치(채널별 2200W 주의 / 2860W 위험) 초과 시 "
        "Celery 태스크가 알람 생성. -1은 통신 불능 채널."
    ),
    responses=_COMMON_RESPONSES,
)
async def recv_watt(payload: PowerWattPayload, bg: BackgroundTasks):
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
