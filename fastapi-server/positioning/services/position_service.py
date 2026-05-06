# positioning/services/position_service.py — 작업자 위치 DRF 저장 서비스
#
# 수신된 작업자 위치를 DRF에 전달해 지오펜스 근접 판정 및 DB 저장을 요청한다.
# 지오펜스 경계 30px 이내 접근 시에만 DRF에서 DB 레코드를 생성한다.
# 더미 시뮬레이션은 dummies/position_dummy.py 에서 담당한다.
import logging

from positioning.schemas.position import WorkerPositionSchema
from services.drf_client import post_to_drf

logger = logging.getLogger(__name__)

DRF_POSITION_PATH = "/api/positioning/receive/"


async def save_positions_to_drf(
    positions: list[WorkerPositionSchema],
) -> dict[int, dict]:
    """
    작업자 위치 목록을 DRF에 저장 요청.

    DRF 측에서 지오펜스 근접(30px 이내) 여부를 판단해 DB 저장 여부를 결정하고,
    작업자별 실시간 위험도(센서 기반)와 진입 지오펜스명을 응답에 포함한다.

    DRF 통신 실패는 호출자(브로드캐스트 흐름)에 영향을 주지 않도록 예외를 전파하지 않고
    logger로만 남긴다.

    Returns:
        {worker_id: {"risk_level": str, "zone_name": str | None}}
        통신 실패 시 빈 dict.
    """
    payload = [
        {
            "worker_id": p.worker_id,
            "facility_id": p.facility_id,
            "x": p.x,
            "y": p.y,
            "movement_status": p.movement_status,
            "measured_at": p.measured_at.isoformat(),
        }
        for p in positions
    ]

    res = await post_to_drf(
        DRF_POSITION_PATH,
        payload,
        raise_on_error=False,
        log_category="position_service",
    )
    statuses_map: dict[int, dict] = {}
    if res is not None and res.status_code == 201:
        body = res.json()
        for s in body.get("statuses", []):
            statuses_map[s["worker_id"]] = {
                "risk_level": s.get("risk_level", "normal"),
                "zone_name": s.get("zone_name"),
            }
        saved = body.get("saved", 0)
        if saved > 0:
            logger.info(
                f"[position_service] action=saved sent={len(payload)} saved={saved}"
            )
    return statuses_map
