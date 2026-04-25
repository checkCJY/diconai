# gas/routers/gas_router.py — 가스 센서 HTTP 수신 엔드포인트
#
# 가스 센서 장비(에어위드)로부터 데이터를 수신하는 라우터.
# 수신된 데이터는 gas_service로 위임해 처리한다.
#   POST /api/sensors/info : 장비 부팅 시 1회 전송하는 기기 식별 정보 수신
#   POST /api/sensors/gas  : 1초 주기로 전송되는 가스 측정값 수신
from fastapi import APIRouter

from gas.schemas.gas import DeviceInfoPayload, GasDataPayload
from gas.services.gas_service import process_gas_data

router = APIRouter(prefix="/api/sensors", tags=["sensors"])


@router.post("/info")
async def receive_device_info(payload: DeviceInfoPayload):
    """기기 부팅 시 1회 전송되는 식별 정보를 수신한다. 현재는 확인 응답만 반환."""
    return {"received": True, "device_id": payload.device_id}


@router.post("/gas")
async def receive_gas_data(payload: GasDataPayload):
    """가스 측정값을 수신해 DRF 저장 및 WebSocket 공유 상태 갱신을 처리한다."""
    return await process_gas_data(payload)
