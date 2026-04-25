# gas/routers/gas_router.py — 가스 센서 HTTP 수신 엔드포인트
from fastapi import APIRouter

from gas.schemas.gas import DeviceInfoPayload, GasDataPayload
from gas.services.gas_service import process_gas_data

router = APIRouter(prefix="/api/sensors", tags=["sensors"])


@router.post("/info")
async def receive_device_info(payload: DeviceInfoPayload):
    return {"received": True, "device_id": payload.device_id}


@router.post("/gas")
async def receive_gas_data(payload: GasDataPayload):
    return await process_gas_data(payload)
