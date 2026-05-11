# dummies/gas_dummy.py — 가스 센서 더미 데이터 전송 스크립트
#
# 실제 에어위드 가스 센서 장비 대신 FastAPI 엔드포인트에 더미 데이터를 1초 주기로 전송한다.
# 기동 시 /api/sensors/info 에 장비 식별 정보를 1회 전송하고,
# 이후 /api/sensors/gas 에 가스 측정값을 반복 전송한다.
#
# [시나리오 기반 이상 생성 — v2]
# 기존: 가스별 독립 확률 샘플링 → 이상 레코드에서 가스 1~2개만 위험, 나머지 정상
#       → Isolation Forest가 "거의 정상"으로 오판 (멀티변수 패턴 미형성)
# 변경: 실제 사고 유형을 시나리오로 모델링 → 관련 가스들이 함께 이상 범위로 이동
#       → IF가 멀티변수 상관 패턴을 학습해 정확도 90%+ 기대
#
# mixed 모드: DANGER_EVENT_PROB 확률로 4종 시나리오 중 1개를 무작위 선택
#             나머지 확률은 전 가스 정상 레코드
# fixed 모드(normal/warning/danger): 기존 동작 유지 (전 가스 동일 레벨)
#
# 실행: python -m dummies.gas_dummy

import logging
import random
import time
from datetime import datetime, timezone

import requests

from core.config import settings
from core.gas_thresholds import calculate_gas_status
from dummies._scenario import get_scenario_mode

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

FASTAPI_BASE_URL = f"http://{settings.DUMMY_TARGET_HOST}:{settings.DUMMY_TARGET_PORT}"
FASTAPI_DEVICE_INFO_URL = f"{FASTAPI_BASE_URL}/api/sensors/info"
FASTAPI_GAS_URL = f"{FASTAPI_BASE_URL}/api/sensors/gas"

DEVICE_ID = "63200c3afd12"
DEVICE_NAME = "63200c3afd12"
SOFTWARE_VERSION = "1.0.1"
SENSOR_LOCATION = {"x": 140, "y": 160}
DANGER_EVENT_PROB = (
    settings.DUMMY_RISK_PROBABILITY
)  # .env DUMMY_RISK_PROBABILITY로 제어

GAS_NORMAL_RANGE: dict[str, tuple] = {
    "co": (0, 24),
    "h2s": (0, 9),
    "co2": (400, 999),
    "o2": (19.0, 21.0),
    "lel": (0, 5),
    "no2": (0.0, 2.9),
    "so2": (0.0, 1.9),
    "o3": (0.0, 0.059),
    "nh3": (0, 24),
    "voc": (0.0, 0.49),
}

GAS_WARNING_RANGE: dict[str, tuple] = {
    "co": (26, 199),  # normal_max(25)~warning_max(200) 사이
    "h2s": (10, 14),
    "co2": (1001, 4999),
    "o2": (16.0, 17.9),  # 정상하한(18)~위험하한(16)
    "lel": (0, 5),  # lel은 임계치 미정의 → 정상 유지
    "no2": (3.1, 4.9),
    "so2": (2.1, 4.9),
    "o3": (0.061, 0.119),
    "nh3": (26, 34),
    "voc": (0.51, 0.99),
}

GAS_DANGER_RANGE: dict[str, tuple] = {
    "co": (200, 300),
    "h2s": (15, 50),
    "co2": (5000, 8000),
    "o2": (10.0, 15.0),
    "lel": (10, 30),
    "no2": (5.0, 10.0),
    "so2": (5.0, 10.0),
    "o3": (0.12, 0.30),
    "nh3": (35, 70),
    "voc": (1.0, 2.0),
}

_RANGE_BY_LEVEL = {
    "normal": GAS_NORMAL_RANGE,
    "warning": GAS_WARNING_RANGE,
    "danger": GAS_DANGER_RANGE,
}

# ---------------------------------------------------------------------------
# 시나리오 정의 — 실제 사고 유형별 가스 위험도 패턴
#
# 각 시나리오는 {가스명: 레벨} 매핑이다.
# 명시된 가스만 해당 레벨로 샘플링하고, 나머지는 모두 "normal"로 샘플링한다.
#
# co_leak     : 일산화탄소 누출 (연소 부족/환기 불량)
#               co↑(danger) + co2↑(warning, 산소소비) + o2↓(warning, 산소결핍)
# h2s_leak    : 황화수소 누출 (하수/화학약품)
#               h2s↑(danger) + o2↓(warning) + so2↑(warning, h2s 산화부산물)
# fire        : 화재/폭발 전조 (lel 상승 + 연소가스)
#               lel↑(danger) + co↑(warning) + co2↑(danger) + o2↓(danger) + voc↑(warning)
# chemical_spill : 유해화학물 다중 누출
#               no2↑(danger) + so2↑(danger) + nh3↑(danger) + o3↑(warning) + voc↑(danger)
# ---------------------------------------------------------------------------
SCENARIOS: dict[str, dict[str, str]] = {
    "co_leak": {
        "co": "danger",
        "co2": "warning",
        "o2": "warning",
    },
    "h2s_leak": {
        "h2s": "danger",
        "o2": "warning",
        "so2": "warning",
    },
    "fire": {
        "lel": "danger",
        "co": "warning",
        "co2": "danger",
        "o2": "danger",
        "voc": "warning",
    },
    "chemical_spill": {
        "no2": "danger",
        "so2": "danger",
        "nh3": "danger",
        "o3": "warning",
        "voc": "danger",
    },
}

_SCENARIO_NAMES = list(SCENARIOS.keys())


def _build_scenario_levels(mode: str) -> dict[str, str]:
    """모드에 따라 가스별 위험도 레벨 매핑을 반환한다.

    fixed 모드(normal/warning/danger): 전 가스를 동일 레벨로 설정.
    mixed 모드: DANGER_EVENT_PROB 확률로 시나리오 1개를 무작위 선택해 적용.
               시나리오에 포함되지 않은 가스는 normal 유지.
               나머지 확률은 전 가스 normal.
    """
    all_gases = list(GAS_NORMAL_RANGE.keys())

    if mode in ("normal", "warning", "danger"):
        return {gas: mode for gas in all_gases}

    # mixed 모드 — 시나리오 기반
    if random.random() < DANGER_EVENT_PROB:
        scenario = SCENARIOS[random.choice(_SCENARIO_NAMES)]
        return {gas: scenario.get(gas, "normal") for gas in all_gases}

    return {gas: "normal" for gas in all_gases}


def _pick_value(gas: str, level: str) -> float | int:
    """가스 종류와 위험도 라벨에 따라 해당 범위 내 랜덤값을 반환한다."""
    low, high = _RANGE_BY_LEVEL[level][gas]
    if isinstance(low, float) or isinstance(high, float):
        return round(random.uniform(low, high), 2)
    return random.randint(int(low), int(high))


def generate_device_info() -> dict:
    """FastAPI /api/sensors/info 에 전송할 장비 식별 정보 페이로드를 생성한다."""
    return {
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
        "software_version": SOFTWARE_VERSION,
        "location": SENSOR_LOCATION,
    }


def generate_gas_data() -> dict:
    """FastAPI /api/sensors/gas 에 전송할 가스 측정값 페이로드를 생성한다.

    시나리오 모드(mixed/normal/warning/danger)에 따라 범위가 결정된다.
    mixed 모드: DANGER_EVENT_PROB 확률로 사고 시나리오 1종을 선택해
               관련 가스들이 함께 위험 범위로 이동 (상관 패턴 형성).
    fixed 모드(normal/warning/danger): 전 가스가 동일 위험도 범위에서 랜덤 샘플링.
    """
    mode = get_scenario_mode()
    levels = _build_scenario_levels(mode)
    gas_values = {gas: _pick_value(gas, levels[gas]) for gas in GAS_NORMAL_RANGE}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
        "location": SENSOR_LOCATION,
        **gas_values,
        "status": calculate_gas_status(gas_values),
    }


def send_data(url: str, payload: dict, label: str) -> None:
    """지정한 URL에 payload를 POST로 전송하고 결과를 로깅한다."""
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=5,
        )
        logger.info(
            "[%s] HTTP %s | %s", label, response.status_code, payload.get("status", "-")
        )
    except requests.exceptions.ConnectionError:
        logger.error("[%s] 연결 실패 (URL: %s)", label, url)
    except requests.exceptions.Timeout:
        logger.error("[%s] 응답 시간 초과", label)
    except Exception as exc:
        logger.error("[%s] 전송 실패 — %s", label, exc)


def run() -> None:
    """더미 전송 루프를 시작한다.

    장비 정보를 1회 전송한 뒤 1초마다 가스 데이터를 반복 전송한다.
    DANGER_EVENT_PROB 확률로 위험 데이터를 섞어 알람 시나리오를 테스트할 수 있다.
    """
    logger.info(
        "=== 가스 더미 전송 시작 (시나리오 모드 v2 | 위험 확률: %d%% | 시나리오: %s) ===",
        int(DANGER_EVENT_PROB * 100),
        ", ".join(_SCENARIO_NAMES),
    )
    send_data(FASTAPI_DEVICE_INFO_URL, generate_device_info(), "DEVICE_INFO")
    logger.info("가스 데이터 전송 시작 → %s", FASTAPI_GAS_URL)
    while True:
        send_data(FASTAPI_GAS_URL, generate_gas_data(), "GAS")
        time.sleep(settings.DUMMY_SEND_INTERVAL_SEC)


if __name__ == "__main__":
    run()
