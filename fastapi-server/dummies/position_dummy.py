# dummies/position_dummy.py — 작업자 위치 더미 데이터 전송 스크립트
#
# 실제 IoT 위치 장비 대신 FastAPI 위치 수신 엔드포인트에 더미 위치 데이터를 1초 주기로 전송한다.
# DUMMY_WORKERS에 정의된 4명의 작업자가 설비 도면 경계 안에서 이동하며,
# 경계(x: 0~1290, y: 0~590)에 닿으면 방향을 반전시킨다.
# 실행: python -m dummies.position_dummy

import logging
import random
import time
from datetime import datetime, timezone

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

FASTAPI_BASE_URL = "http://localhost:8001"
FASTAPI_POSITION_URL = f"{FASTAPI_BASE_URL}/api/positioning/receive"

DUMMY_WORKERS: list[dict] = [
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


def _step_worker(w: dict) -> None:
    """한 틱(1초)만큼 작업자 위치를 이동시킨다. 경계에 닿으면 방향을 반전한다."""
    if w["movement_status"] != "moving":
        return
    w["x"] += w["dx"] + (random.random() - 0.5) * 3
    w["y"] += w["dy"] + (random.random() - 0.5) * 3
    if w["x"] <= 0 or w["x"] >= 1290:
        w["dx"] *= -1
    if w["y"] <= 0 or w["y"] >= 590:
        w["dy"] *= -1
    w["x"] = max(0.0, min(1290.0, w["x"]))
    w["y"] = max(0.0, min(590.0, w["y"]))


def generate_positions() -> list[dict]:
    """현재 DUMMY_WORKERS 상태를 FastAPI 수신 포맷으로 변환해 반환한다."""
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "worker_id": w["worker_id"],
            "worker_name": w["worker_name"],
            "facility_id": w["facility_id"],
            "x": round(w["x"], 2),
            "y": round(w["y"], 2),
            "movement_status": w["movement_status"],
            "measured_at": now,
        }
        for w in DUMMY_WORKERS
    ]


def send_data(url: str, payload: list[dict], label: str) -> None:
    """지정한 URL에 payload를 POST로 전송하고 결과를 로깅한다."""
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=5,
        )
        logger.info("[%s] HTTP %s | %d명", label, response.status_code, len(payload))
    except requests.exceptions.ConnectionError:
        logger.error("[%s] 연결 실패 (URL: %s)", label, url)
    except requests.exceptions.Timeout:
        logger.error("[%s] 응답 시간 초과", label)
    except Exception as exc:
        logger.error("[%s] 전송 실패 — %s", label, exc)


def run() -> None:
    """더미 전송 루프를 시작한다. 1초마다 위치를 갱신하고 FastAPI에 전송한다."""
    logger.info("=== 위치 더미 전송 시작 ===")
    while True:
        for w in DUMMY_WORKERS:
            _step_worker(w)
        payload = generate_positions()
        send_data(FASTAPI_POSITION_URL, payload, "POSITION")
        time.sleep(1)


if __name__ == "__main__":
    run()
