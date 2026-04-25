# gas/services/gas_service.py — 가스 데이터 DRF 전송 + 공유 상태 갱신
import logging

import httpx
from fastapi import HTTPException

from core.config import settings
from core.gas_thresholds import calculate_individual_risks
from gas.schemas.gas import GasDataPayload
from websocket.state import active_alarms, latest_gas_snapshot

logger = logging.getLogger(__name__)

DRF_GAS_URL = f"{settings.DRF_BASE_URL}/api/monitoring/gas/"


async def _forward_to_drf(drf_payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(DRF_GAS_URL, json=drf_payload)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="등록되지 않은 장치입니다.")
        if response.status_code >= 400:
            logger.error("DRF 저장 실패 | %s | %s", response.status_code, response.text)
            raise HTTPException(status_code=502, detail="데이터 저장에 실패했습니다.")
        return response.json()
    except httpx.ConnectError:
        logger.error("DRF 연결 실패 (%s)", DRF_GAS_URL)
        raise HTTPException(status_code=503, detail="DRF 서버에 연결할 수 없습니다.")
    except httpx.TimeoutException:
        logger.error("DRF 응답 시간 초과")
        raise HTTPException(status_code=504, detail="DRF 서버 응답 시간 초과.")


async def process_gas_data(payload: GasDataPayload) -> dict:
    """
    가스 데이터 처리 흐름:
      1. DRF에 측정값 저장
      2. 공유 상태 직접 갱신 (HTTP Push 없음)
         - latest_gas_snapshot: 브로드캐스트 페이로드에 spread
         - active_alarms: 다음 WS 틱에 포함 후 소비
    """
    gas_values = {
        "o2": payload.o2,
        "co": payload.co,
        "co2": payload.co2,
        "h2s": payload.h2s,
        "lel": payload.lel,
        "no2": payload.no2,
        "so2": payload.so2,
        "o3": payload.o3,
        "nh3": payload.nh3,
        "voc": payload.voc,
    }
    individual_risks = calculate_individual_risks(gas_values)

    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": payload.timestamp.isoformat(),
        "co": payload.co,
        "h2s": payload.h2s,
        "co2": payload.co2,
        "o2": payload.o2,
        "no2": payload.no2,
        "so2": payload.so2,
        "o3": payload.o3,
        "nh3": payload.nh3,
        "voc": payload.voc,
        **individual_risks,
        "raw_payload": payload.model_dump(mode="json"),
    }

    drf_data = await _forward_to_drf(drf_payload)
    alarms = drf_data.get("alarms", [])

    # 공유 상태 직접 갱신 (websocket/state.py)
    gas_snapshot = {
        "co": payload.co,
        "h2s": payload.h2s,
        "co2": payload.co2,
        "o2": payload.o2,
        "no2": payload.no2,
        "so2": payload.so2,
        "o3": payload.o3,
        "nh3": payload.nh3,
        "voc": payload.voc,
        **individual_risks,
    }
    latest_gas_snapshot.update(gas_snapshot)
    if alarms:
        active_alarms.extend(alarms)

    return {
        "received": True,
        "device_id": payload.device_id,
        "status": payload.status,
        **individual_risks,
    }
