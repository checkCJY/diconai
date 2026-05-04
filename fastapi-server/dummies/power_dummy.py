# dummies/power_dummy.py — 전력 센서 더미 데이터 전송 스크립트
#
# 실제 전력 센서 장비 대신 FastAPI 전력 엔드포인트에 더미 데이터를 3초 주기로 전송한다.
# 한 루프에서 onoff → current → voltage → watt 순으로 4개 엔드포인트에 순차 전송한다.
# 이는 실제 장비 프로토콜(동일 device_id가 측정 타입별로 분리 전송)을 그대로 재현한 것이다.
# 실행: python -m dummies.power_dummy

import logging
import random
import time

import requests

from core.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

FASTAPI_BASE_URL = f"http://{settings.DUMMY_TARGET_HOST}:{settings.DUMMY_TARGET_PORT}"
FASTAPI_POWER_ONOFF_URL = f"{FASTAPI_BASE_URL}/api/power/onoff"
FASTAPI_POWER_CURRENT_URL = f"{FASTAPI_BASE_URL}/api/power/current"
FASTAPI_POWER_VOLTAGE_URL = f"{FASTAPI_BASE_URL}/api/power/voltage"
FASTAPI_POWER_WATT_URL = f"{FASTAPI_BASE_URL}/api/power/watt"

DEVICE_ID = "63200c3afd12"

POWER_CHANNELS = [
    "slave01",
    "slave02",
    "slave11",
    "slave12",
    "slave21",
    "slave22",
    "slave31",
    "slave32",
    "slave41",
    "slave42",
    "slave51",
    "slave52",
    "slave61",
    "slave62",
    "slave71",
    "slave72",
]

SEND_INTERVAL_SEC = 3


def generate_power_onoff_data() -> dict:
    """16채널 ON/OFF 상태 페이로드를 생성한다. 70% 확률로 ON(255), 나머지는 OFF(0)."""
    data = {"device_id": DEVICE_ID}
    for ch in POWER_CHANNELS:
        data[ch] = 255 if random.random() < 0.7 else 0
    return data


def generate_power_current_data() -> dict:
    """16채널 전류(A) 페이로드를 생성한다. 채널별로 1~30A 또는 0A를 랜덤 배정한다."""
    data = {"device_id": DEVICE_ID}
    for ch in POWER_CHANNELS:
        data[ch] = random.randint(1, 30) if random.random() < 0.5 else 0
    return data


def generate_power_voltage_data() -> dict:
    """16채널 전압(V) 페이로드를 생성한다. 채널별로 215~225V 또는 0V를 랜덤 배정한다."""
    data = {"device_id": DEVICE_ID}
    for ch in POWER_CHANNELS:
        data[ch] = random.randint(215, 225) if random.random() < 0.5 else 0
    return data


def generate_power_watt_data() -> dict:
    """16채널 전력(W) 페이로드를 생성한다. 채널별로 50~5000W 또는 0W를 랜덤 배정한다."""
    data = {"device_id": DEVICE_ID}
    for ch in POWER_CHANNELS:
        data[ch] = random.randint(50, 5000) if random.random() < 0.5 else 0
    return data


def send_data(url: str, payload: dict, label: str) -> None:
    """지정한 URL에 payload를 POST로 전송하고 결과를 로깅한다."""
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=5,
        )
        logger.info("[%s] HTTP %s", label, response.status_code)
    except requests.exceptions.ConnectionError:
        logger.error("[%s] 연결 실패 (URL: %s)", label, url)
    except requests.exceptions.Timeout:
        logger.error("[%s] 응답 시간 초과", label)
    except Exception as exc:
        logger.error("[%s] 전송 실패 — %s", label, exc)


def run() -> None:
    """더미 전송 루프를 시작한다.

    SEND_INTERVAL_SEC 주기로 onoff → current → voltage → watt 순서로 전송한다.
    """
    logger.info("=== 전력 더미 전송 시작 (주기: %ds) ===", SEND_INTERVAL_SEC)
    while True:
        send_data(FASTAPI_POWER_ONOFF_URL, generate_power_onoff_data(), "POWER_ONOFF")
        send_data(
            FASTAPI_POWER_CURRENT_URL, generate_power_current_data(), "POWER_CURRENT"
        )
        send_data(
            FASTAPI_POWER_VOLTAGE_URL, generate_power_voltage_data(), "POWER_VOLTAGE"
        )
        send_data(FASTAPI_POWER_WATT_URL, generate_power_watt_data(), "POWER_WATT")
        time.sleep(SEND_INTERVAL_SEC)


if __name__ == "__main__":
    run()
