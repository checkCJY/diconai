# fastapi-server/positioning/services/position_service.py
import random
import httpx
from datetime import datetime, timezone
from positioning.schemas.position import WorkerPositionSchema

DRF_BASE_URL = "http://127.0.0.1:8000"

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
                f"{DRF_BASE_URL}/api/positioning/receive/",
                json=payload,
                timeout=5.0,
            )
            if res.status_code != 201:
                print(f"[positioning] DRF 저장 실패: {res.status_code} {res.text}")
            else:
                saved_count = res.json().get("saved", 0)
                if saved_count > 0:
                    print(f"[positioning] DRF 저장 완료: {saved_count}명")

    except Exception as e:
        print(f"[positioning] DRF 저장 오류: {e}")
