# gas/services/gas_service.py — 가스 데이터 처리 서비스
#
# 가스 센서 수신 데이터의 비즈니스 로직을 담당한다.
#   1. DRF에 측정값을 저장한다.
#   2. DRF 응답에서 알람 목록을 꺼내 active_alarms에 추가한다.
#   3. latest_gas_snapshot을 갱신해 다음 WebSocket 틱에 브라우저로 전달한다.
#
# HTTP Push(/internal/*) 없이 websocket/state.py를 직접 갱신하는 방식을 사용한다.
import logging

import httpx
from fastapi import HTTPException

from core.config import settings
from core.gas_thresholds import calculate_individual_risks
from gas.schemas.gas import GasDataPayload
from datetime import datetime, timezone

from websocket.state import active_alarms, gas_latest, latest_gas_snapshot

logger = logging.getLogger(__name__)

DRF_GAS_URL = f"{settings.DRF_BASE_URL}/api/monitoring/gas/"


async def _forward_to_drf(drf_payload: dict) -> dict:
    """
    DRF 가스 저장 엔드포인트에 측정값을 전달하고 응답을 반환한다.
    연결 실패·타임아웃·4xx 오류 시 적절한 HTTPException을 발생시켜
    센서 장비에 오류 응답을 반환한다.
    """
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
    가스 데이터 수신 후 전체 처리 흐름을 조율한다.

    1. 가스별 위험도(individual_risks)를 계산한다.
    2. DRF에 측정값과 위험도를 저장하고 알람 목록을 받는다.
    3. latest_gas_snapshot을 갱신해 WebSocket 브로드캐스트에 포함시킨다.
    4. 새 알람이 있으면 active_alarms에 추가해 다음 WS 틱에 브라우저로 전달한다.
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
    gas_latest["updated_at"] = datetime.now(timezone.utc).isoformat()
    if alarms:
        active_alarms.extend(alarms)

    return {
        "received": True,
        "device_id": payload.device_id,
        "status": payload.status,
        **individual_risks,
    }
