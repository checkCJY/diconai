"""
가스 센서 더미 데이터 생성 및 전송 스크립트.

실제 센서 장비 없이 FastAPI 수신 엔드포인트로 테스트 데이터를 전송한다.

전송 타입:
  - 기기 정보   : 스크립트 시작 시 1회 (부팅 시뮬레이션)
  - 가스 데이터 : 1초마다 반복 전송

프로토콜 참고: 에어위드 HTTP 프로토콜 v1.0.1
  원본 필드: device_id, o2, co, co2, h2s, lel
  확장 필드: no2, so2, o3, nh3, voc, location, status, timestamp
"""

import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))

from core.gas_thresholds import calculate_gas_status


# ============================================================
# 로거
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# FastAPI 엔드포인트
# ============================================================

FASTAPI_DEVICE_INFO_URL = "http://localhost:8000/api/sensors/info"
FASTAPI_GAS_URL = "http://localhost:8000/api/sensors/gas"


# ============================================================
# 기기 고정 설정
# ============================================================

DEVICE_ID = "63200c3afd12"
DEVICE_NAME = "63200c3afd12"
SOFTWARE_VERSION = "1.0.1"
SENSOR_LOCATION = {"x": 140, "y": 160}

DANGER_EVENT_PROB = 0.1  # 10% 확률로 위험 이벤트 강제 생성


# ============================================================
# 더미 값 생성 범위
# ============================================================

GAS_NORMAL_RANGE: dict[str, tuple] = {
    "co":  (0,    24),
    "h2s": (0,    9),
    "co2": (400,  999),
    "o2":  (19.0, 21.0),
    "lel": (0,    5),
    "no2": (0.0,  2.9),
    "so2": (0.0,  1.9),
    "o3":  (0.0,  0.059),
    "nh3": (0,    24),
    "voc": (0.0,  0.49),
}

GAS_DANGER_RANGE: dict[str, tuple] = {
    "co":  (200,  300),
    "h2s": (15,   50),
    "co2": (5000, 8000),
    "o2":  (10.0, 15.0),
    "lel": (10,   30),
    "no2": (5.0,  10.0),
    "so2": (5.0,  10.0),
    "o3":  (0.12, 0.30),
    "nh3": (35,   70),
    "voc": (1.0,  2.0),
}


# ============================================================
# 데이터 생성
# ============================================================

def _pick_value(gas: str, is_danger: bool) -> float | int:
    """정상/위험 구간에서 랜덤 측정값을 반환한다."""
    low, high = (GAS_DANGER_RANGE if is_danger else GAS_NORMAL_RANGE)[gas]
    if isinstance(low, float) or isinstance(high, float):
        return round(random.uniform(low, high), 2)
    return random.randint(int(low), int(high))


def generate_device_info() -> dict:
    """기기 식별 정보 페이로드."""
    return {
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
        "software_version": SOFTWARE_VERSION,
        "location": SENSOR_LOCATION,
    }


def generate_gas_data(is_danger: bool = False) -> dict:
    """
    가스 센서 측정값 페이로드.

    sample:
        {
            "timestamp": "2026-04-21T10:00:00",
            "device_id": "63200c3afd12",
            "device_name": "63200c3afd12",
            "location": {"x": 140, "y": 160},
            "o2": 20.15, "co": 12, "co2": 560, "h2s": 4, "lel": 2,
            "no2": 1.2, "so2": 0.8, "o3": 0.02, "nh3": 8, "voc": 0.3,
            "status": "normal"
        }
    """
    gas_values = {gas: _pick_value(gas, is_danger) for gas in GAS_NORMAL_RANGE}

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
        "location": SENSOR_LOCATION,
        **gas_values,
        "status": calculate_gas_status(gas_values),
    }


# ============================================================
# 전송
# ============================================================

def send_data(url: str, payload: dict, label: str) -> None:
    """JSON 페이로드를 지정 URL로 POST 전송한다."""
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=5,
        )
        logger.info(
            "[%s] HTTP %s | status=%s | %s",
            label, response.status_code, payload.get("status", "-"), payload,
        )
    except requests.exceptions.ConnectionError:
        logger.error("[%s] 연결 실패 — 서버 실행 여부 확인 (URL: %s)", label, url)
    except requests.exceptions.Timeout:
        logger.error("[%s] 응답 시간 초과 (5초)", label)
    except Exception as exc:
        logger.error("[%s] 전송 실패 — %s", label, exc)


# ============================================================
# 메인 루프
# ============================================================

def run() -> None:
    """
    기기 정보를 1회 전송한 후 가스 데이터를 1초마다 반복 전송한다.
    Ctrl+C로 종료.
    """
    logger.info("=== 더미 데이터 전송 시작 (위험 이벤트 확률: %d%%) ===", int(DANGER_EVENT_PROB * 100))

    # STEP 1. 기기 정보 1회
    send_data(FASTAPI_DEVICE_INFO_URL, generate_device_info(), "DEVICE_INFO")

    # STEP 2. 가스 데이터 반복
    logger.info("가스 데이터 전송 시작 → %s", FASTAPI_GAS_URL)
    while True:
        is_danger = random.random() < DANGER_EVENT_PROB
        send_data(FASTAPI_GAS_URL, generate_gas_data(is_danger), "GAS")
        time.sleep(1)


if __name__ == "__main__":
    run()
