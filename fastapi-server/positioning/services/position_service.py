# positioning/services/position_service.py — 더미 작업자 위치 시뮬레이션 및 DRF 저장
#
# 실제 IoT 위치 장비 연동 전까지 사용하는 더미 시뮬레이션 서비스.
# DUMMY_WORKERS에 정의된 4명의 작업자가 설비 도면 경계 안에서 이동한다.
# DRF 저장은 지오펜스 경계 30px 이내 접근 시에만 DB 레코드가 생성된다.
import random
import httpx
from datetime import datetime, timezone
from positioning.schemas.position import WorkerPositionSchema

from core.config import settings

# 더미 작업자 목록 (초기 위치 + 이동 방향)
DUMMY_WORKERS = [
    {
        "worker_id": 1,
        "worker_name": "작업자 A",
        "facility_id": 1,
        "x": 150.0,
        "y": 120.0,
        "dx": 4.0,
        "dy": 2.0,
        "movement_status": "moving",
    },
    {
        "worker_id": 2,
        "worker_name": "작업자 B",
        "facility_id": 1,
        "x": 600.0,
        "y": 350.0,
        "dx": -3.0,
        "dy": 4.0,
        "movement_status": "moving",
    },
    {
        "worker_id": 3,
        "worker_name": "작업자 C",
        "facility_id": 1,
        "x": 950.0,
        "y": 200.0,
        "dx": 0.0,
        "dy": 0.0,
        "movement_status": "stationary",
    },
    {
        "worker_id": 4,
        "worker_name": "작업자 D",
        "facility_id": 1,
        "x": 350.0,
        "y": 480.0,
        "dx": 5.0,
        "dy": -3.0,
        "movement_status": "moving",
    },
]


def update_worker_positions() -> list[WorkerPositionSchema]:
    """
    DUMMY_WORKERS의 위치를 한 틱(1초) 만큼 이동시키고 WorkerPositionSchema 목록을 반환한다.

    이동 중인 작업자는 dx/dy 벡터에 미세한 랜덤 흔들림을 더해 자연스러운 이동을 시뮬레이션한다.
    경계(x: 0~1290, y: 0~590)에 닿으면 방향을 반전시킨다.
    """
    positions = []
    now = datetime.now(timezone.utc)

    for w in DUMMY_WORKERS:
        if w["movement_status"] == "moving":
            w["x"] += w["dx"] + (random.random() - 0.5) * 3
            w["y"] += w["dy"] + (random.random() - 0.5) * 3

            if w["x"] <= 0 or w["x"] >= 1290:
                w["dx"] *= -1
            if w["y"] <= 0 or w["y"] >= 590:
                w["dy"] *= -1
            w["x"] = max(0.0, min(1290.0, w["x"]))
            w["y"] = max(0.0, min(590.0, w["y"]))

        positions.append(
            WorkerPositionSchema(
                worker_id=w["worker_id"],
                worker_name=w["worker_name"],
                facility_id=w["facility_id"],
                x=round(w["x"], 2),
                y=round(w["y"], 2),
                movement_status=w["movement_status"],
                measured_at=now,
            )
        )

    return positions


async def save_positions_to_drf(positions: list[WorkerPositionSchema]):
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
