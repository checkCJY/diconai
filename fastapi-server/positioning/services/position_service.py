# positioning/services/position_service.py — 작업자 위치 DRF 저장 서비스
#
# 수신된 작업자 위치를 DRF에 전달해 지오펜스 근접 판정 및 DB 저장을 요청한다.
# 지오펜스 경계 30px 이내 접근 시에만 DRF에서 DB 레코드를 생성한다.
# 더미 시뮬레이션은 dummies/position_dummy.py 에서 담당한다.
import httpx
from positioning.schemas.position import WorkerPositionSchema
from core.config import settings


async def save_positions_to_drf(positions: list[WorkerPositionSchema]) -> None:
    """
    작업자 위치 목록을 DRF에 전송한다.

    DRF 측에서 지오펜스 근접(30px 이내) 여부를 판단해 DB 저장 여부를 결정한다.
    응답 body의 saved 값이 실제 저장 건수이며, HTTP 201이어도 0일 수 있다.
    """
    try:
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

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{settings.DRF_BASE_URL}/api/positioning/receive/",
                json=payload,
                timeout=5.0,
            )
            if res.status_code != 201:
                print(f"[positioning] DRF 저장 실패: {res.status_code} {res.text}")
            else:
                saved = res.json().get("saved", 0)
                if saved > 0:
                    print(f"[positioning] 전송: {len(payload)}명, 저장: {saved}명")

    except Exception as e:
        print(f"[positioning] DRF 저장 오류: {e}")
