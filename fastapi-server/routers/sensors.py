import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException

from core.config import settings
from core.gas_thresholds import calculate_individual_risks
from schemas.sensors import DeviceInfoPayload, GasDataPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sensors", tags=["sensors"])

DRF_GAS_URL = f"{settings.DRF_BASE_URL}/api/monitoring/gas/"
WS_ALARM_URL = f"{settings.FASTAPI_WS_BASE_URL}/internal/alarm/"
WS_GAS_SNAPSHOT_URL = f"{settings.FASTAPI_WS_BASE_URL}/internal/gas-snapshot/"


@router.post("/info")
async def receive_device_info(payload: DeviceInfoPayload):
    return {"received": True, "device_id": payload.device_id}


@router.post("/gas")
async def receive_gas_data(payload: GasDataPayload):
    gas_values = {
        "o2": payload.o2, "co": payload.co, "co2": payload.co2,
        "h2s": payload.h2s, "lel": payload.lel, "no2": payload.no2,
        "so2": payload.so2, "o3": payload.o3, "nh3": payload.nh3,
        "voc": payload.voc,
    }
    individual_risks = calculate_individual_risks(gas_values)

    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": payload.timestamp.isoformat(),
        # 가스 측정값 9종 (lel 제외)
        "co": payload.co, "h2s": payload.h2s, "co2": payload.co2,
        "o2": payload.o2, "no2": payload.no2, "so2": payload.so2,
        "o3": payload.o3, "nh3": payload.nh3, "voc": payload.voc,
        # 가스별 위험도 9종
        **individual_risks,
        # 원본 페이로드 (lel 포함 전체)
        "raw_payload": payload.model_dump(mode="json"),
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(DRF_GAS_URL, json=drf_payload)

        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="등록되지 않은 장치입니다.")
        if response.status_code >= 400:
            logger.error("DRF 저장 실패 | %s | %s", response.status_code, response.text)
            raise HTTPException(status_code=502, detail="데이터 저장에 실패했습니다.")

        drf_data = response.json()
        alarms = drf_data.get("alarms", [])

        # 가스 스냅샷 + 알람을 WebSocket 앱(8002)으로 Push (실패해도 무시)
        gas_snapshot = {
            "co": payload.co, "h2s": payload.h2s, "co2": payload.co2,
            "o2": payload.o2, "no2": payload.no2, "so2": payload.so2,
            "o3": payload.o3, "nh3": payload.nh3, "voc": payload.voc,
            **individual_risks,
        }
        try:
            async with httpx.AsyncClient(timeout=2.0) as ws_client:
                tasks = [ws_client.post(WS_GAS_SNAPSHOT_URL, json={"snapshot": gas_snapshot})]
                if alarms:
                    tasks.append(ws_client.post(WS_ALARM_URL, json={"alarms": alarms}))
                await asyncio.gather(*tasks)
        except Exception as e:
            logger.warning("WS Push 실패 (무시): %s", e)

    except httpx.ConnectError:
        logger.error("DRF 연결 실패 — 서버 실행 여부 확인 (%s)", DRF_GAS_URL)
        raise HTTPException(status_code=503, detail="DRF 서버에 연결할 수 없습니다.")
    except httpx.TimeoutException:
        logger.error("DRF 응답 시간 초과 (5초)")
        raise HTTPException(status_code=504, detail="DRF 서버 응답 시간 초과.")

    return {
        "received": True,
        "device_id": payload.device_id,
        "status": payload.status,
        **individual_risks,
    }
