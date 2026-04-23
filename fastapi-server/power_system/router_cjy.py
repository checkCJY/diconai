"""
FastAPI → DRF 전력 데이터 수신 라우터.

흐름:
  더미 센서 → POST /api/power/* (FastAPI)
             → Pydantic 검증
             → measured_at 주입 (datetime.now(timezone.utc), naive 사용 금지)
             → POST /monitoring/api/power/* (DRF)

엔드포인트:
  POST /api/power/onoff   → DRF /monitoring/api/power/event/
  POST /api/power/current → DRF /monitoring/api/power/data/
  POST /api/power/voltage → DRF /monitoring/api/power/data/
  POST /api/power/watt    → DRF /monitoring/api/power/data/
"""

import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, status

from power_system.schemas import (
    PowerCurrentPayload,
    PowerOnOffPayload,
    PowerVoltagePayload,
    PowerWattPayload,
)

router = APIRouter(prefix="/api/power", tags=["power"])

DRF_BASE_URL = os.getenv("DRF_BASE_URL", "http://localhost:8000")
DRF_POWER_EVENT_URL = f"{DRF_BASE_URL}/monitoring/api/power/event/"
DRF_POWER_DATA_URL = f"{DRF_BASE_URL}/monitoring/api/power/data/"
DRF_SERVICE_TOKEN = os.getenv("DRF_SERVICE_TOKEN", "")


def _auth_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if DRF_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {DRF_SERVICE_TOKEN}"
    return headers


async def _post_to_drf(url: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            res = await client.post(url, json=payload, headers=_auth_headers())
            if res.status_code in (200, 201):
                return res.json()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"DRF {res.status_code}: {res.text}",
            )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="DRF 응답 타임아웃",
            )


def _now_utc_iso() -> str:
    """timezone-aware UTC 현재 시각을 ISO 문자열로 반환. naive datetime 사용 금지."""
    return datetime.now(timezone.utc).isoformat()


def _to_channel_list(payload) -> list[dict]:
    """
    채널값 딕셔너리 → DRF channels 리스트 변환.
    통신 불능 채널(None): sensor_status='comm_failure', risk_level 미적용
    정상 채널: sensor_status='active', risk_level='normal' 고정 (임계치 미정의)
    """
    return [
        {
            "channel": ch,
            "value": val,
            "sensor_status": "comm_failure" if val is None else "active",
            "risk_level": "normal",
        }
        for ch, val in payload.to_channel_values().items()
    ]


@router.post("/onoff", status_code=status.HTTP_201_CREATED)
async def receive_power_onoff(payload: PowerOnOffPayload):
    """16채널 ON/OFF 스냅샷 수신 → PowerEvent 저장."""
    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": _now_utc_iso(),
        "snapshot": payload.to_snapshot(),
    }
    return await _post_to_drf(DRF_POWER_EVENT_URL, drf_payload)


@router.post("/current", status_code=status.HTTP_201_CREATED)
async def receive_power_current(payload: PowerCurrentPayload):
    """16채널 전류(A) 수신 → PowerData(data_type=current) 저장."""
    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": _now_utc_iso(),
        "data_type": "current",
        "channels": _to_channel_list(payload),
    }
    return await _post_to_drf(DRF_POWER_DATA_URL, drf_payload)


@router.post("/voltage", status_code=status.HTTP_201_CREATED)
async def receive_power_voltage(payload: PowerVoltagePayload):
    """16채널 전압(V) 수신 → PowerData(data_type=voltage) 저장."""
    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": _now_utc_iso(),
        "data_type": "voltage",
        "channels": _to_channel_list(payload),
    }
    return await _post_to_drf(DRF_POWER_DATA_URL, drf_payload)


@router.post("/watt", status_code=status.HTTP_201_CREATED)
async def receive_power_watt(payload: PowerWattPayload):
    """16채널 전력(W) 수신 → PowerData(data_type=watt) 저장."""
    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": _now_utc_iso(),
        "data_type": "watt",
        "channels": _to_channel_list(payload),
    }
    return await _post_to_drf(DRF_POWER_DATA_URL, drf_payload)
