# gas/routers/gas_router.py — 가스 센서 HTTP 수신 엔드포인트
#
# 가스 센서 장비(에어위드)로부터 데이터를 수신하는 라우터.
# 수신된 데이터는 gas_service로 위임해 처리한다.
#   POST /api/sensors/info : 장비 부팅 시 1회 전송하는 기기 식별 정보 수신
#   POST /api/sensors/gas  : 1초 주기로 전송되는 가스 측정값 수신
from fastapi import APIRouter

from core.redis_client import get_redis  # 이성현 추가 — 센서 등록 캐시용
from gas.constants import REGISTERED_GAS_SENSORS_KEY  # 이성현 추가
# 상수를 constants로 제외 순환 X

from gas.schemas.gas import (
    DeviceInfoPayload,
    DeviceInfoResponse,
    GasDataPayload,
    GasDataResponse,
)
from gas.services.gas_service import process_gas_data

router = APIRouter(prefix="/api/sensors", tags=["sensors"])


@router.post(
    "/info",
    response_model=DeviceInfoResponse,
    summary="가스 센서 기기 식별 정보 수신",
    description=(
        "장비 부팅 시 1회 전송되는 기기 식별 정보를 수신한다. "
        "현재는 확인 응답만 반환하며, 추후 장비 등록·인증 절차 추가 예정."
    ),
    responses={
        422: {"description": "페이로드 검증 실패"},
        500: {"description": "서버 내부 오류"},
    },
)
async def receive_device_info(payload: DeviceInfoPayload):
    # 이성현 추가 — 부팅 시 보내는 device_id를 Redis Set에 등록.
    # 가스 수신(STEP 3)에서 이 Set으로 등록 여부를 즉시 확인 → DRF 블로킹 없이 404 판정.
    r = get_redis()
    await r.sadd(REGISTERED_GAS_SENSORS_KEY, payload.device_id)
    return {"received": True, "device_id": payload.device_id}


@router.post(
    "/gas",
    response_model=GasDataResponse,
    summary="가스 측정값 수신",
    description=(
        "IoT 가스 센서가 1초 주기로 전송하는 9종 가스 농도(O₂/CO/CO₂/H₂S/LEL/NO₂/SO₂/O₃/NH₃/VOC)를 수신한다.\n\n"
        "**처리 흐름**:\n"
        "1. Pydantic 검증 + 서버에서 임계치 기준 `status` 재계산\n"
        "2. DRF로 영속화 요청 (`POST /api/monitoring/gas/`)\n"
        "3. WebSocket 공유 상태 갱신 → 다음 broadcast tick에 브라우저로 전달\n"
        "4. 'warning'/'danger' 시 Celery 태스크가 알람 생성"
    ),
    responses={
        422: {"description": "페이로드 검증 실패 (예: o2 범위 초과)"},
        502: {"description": "DRF 저장 실패"},
        503: {"description": "DRF 서버 연결 불가"},
    },
)
async def receive_gas_data(payload: GasDataPayload):
    return await process_gas_data(payload)
