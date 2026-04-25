"""
전력 센서 더미 데이터 전송 스크립트.
실행: python -m dummies.power_dummy
"""

import logging
import random
import time

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

FASTAPI_BASE_URL = "http://localhost:8001"
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
    data = {"device_id": DEVICE_ID}
    for ch in POWER_CHANNELS:
        data[ch] = 255 if random.random() < 0.7 else 0
    return data


def generate_power_current_data() -> dict:
    data = {"device_id": DEVICE_ID}
    for ch in POWER_CHANNELS:
        data[ch] = random.randint(1, 30) if random.random() < 0.5 else 0
    return data


def generate_power_voltage_data() -> dict:
    data = {"device_id": DEVICE_ID}
    for ch in POWER_CHANNELS:
        data[ch] = random.randint(215, 225) if random.random() < 0.5 else 0
    return data


def generate_power_watt_data() -> dict:
    data = {"device_id": DEVICE_ID}
    for ch in POWER_CHANNELS:
        data[ch] = random.randint(50, 5000) if random.random() < 0.5 else 0
    return data


def send_data(url: str, payload: dict, label: str) -> None:
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
