"""
더미 데이터 생성 및 전송 스크립트.

실제 센서 장비 없이 FastAPI 수신 엔드포인트로 테스트 데이터를 전송한다.

전송 타입:
  - 기기 정보 전송     : 스크립트 시작 시 1회 전송 (부팅 시 전송 시뮬레이션)
  - 기기 환경 데이터   : 1초마다 전송 (현재 연동 대상, 가스 9종 + lel)
  - 전력 데이터        : 구현만 해두고 미사용 (전력 장비 연동 단계에서 활성화)

프로토콜 참고: 센서_데이터_http.html (에어위드 HTTP 프로토콜 v1.0.1)
  - 기기 환경 데이터 원본 필드: device_id, o2, co, co2, h2s, lel
  - 확장 필드 (이번 요청): no2, so2, o3, nh3, voc 추가
  - 지오펜스 연산용 필드 추가: location { x, y }
  - 상태 판단 필드 추가: status (normal / warning / danger)
"""

# ============================================================
# 1) 표준 라이브러리
# ============================================================
import logging
import random
import time
from datetime import datetime

# ============================================================
# 2) 서드파티 라이브러리
# ============================================================
import requests

# ============================================================
# 로거 설정
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# FastAPI 엔드포인트 URL
# ============================================================

FASTAPI_DEVICE_INFO_URL = (
    "http://localhost:8000/api/sensors/info"  # 기기 정보 (부팅 시 1회)
)
FASTAPI_GAS_URL = "http://localhost:8000/api/sensors/gas"  # 기기 환경 데이터
FASTAPI_POWER_ONOFF_URL = "http://localhost:8000/api/power/onoff"  # ON/OFF 상태
FASTAPI_POWER_CURRENT_URL = "http://localhost:8000/api/power/current"  # 전류
FASTAPI_POWER_VOLTAGE_URL = "http://localhost:8000/api/power/voltage"  # 전압
FASTAPI_POWER_WATT_URL = "http://localhost:8000/api/power/watt"  # 전력(W)


# ============================================================
# 기기 고정 설정
# ============================================================

# 기기 mac address (프로토콜 문서 형식)
DEVICE_ID = "63200c3afd12"
DEVICE_NAME = "63200c3afd12"  # 기기명 = mac address (프로토콜 규정)
SOFTWARE_VERSION = "1.0.1"

# 지오펜스 좌표: 센서 장비는 고정 위치 (단위: 임의 픽셀 좌표)
# 실제 연동 시 설비 도면 기준 좌표로 교체 필요
SENSOR_LOCATION = {"x": 140, "y": 160}

# 전력 채널 목록 (slave01~slave72: 총 16CH)
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

# 위험 이벤트 발생 확률 (10%)
DANGER_EVENT_PROB = 0.1


# ============================================================
# 가스별 임계치 기준 (가스별 임계치 기준 이미지 문서 기준)
# ============================================================
# 형식: { 가스명: { "normal_max": 정상 상한, "warning_max": 주의 상한 } }
# O2는 낮을수록 위험이므로 별도 처리 (calculate_gas_status 참고)

GAS_THRESHOLDS = {
    "co": {"normal_max": 25, "warning_max": 200},  # ppm
    "h2s": {"normal_max": 10, "warning_max": 15},  # ppm
    "co2": {"normal_max": 1000, "warning_max": 5000},  # ppm
    "o2": {
        "normal_min": 18.0,
        "normal_max": 23.5,  # % (범위형)
        "warning_min": 16.0,
    },
    "no2": {"normal_max": 3, "warning_max": 5},  # ppm
    "so2": {"normal_max": 2, "warning_max": 5},  # ppm
    "o3": {"normal_max": 0.06, "warning_max": 0.12},  # ppm
    "nh3": {"normal_max": 25, "warning_max": 35},  # ppm
    "voc": {"normal_max": 0.5, "warning_max": 1.0},  # ppm
}

# 정상 구간 생성 범위
GAS_NORMAL_RANGE = {
    "co": (0, 24),
    "h2s": (0, 9),
    "co2": (400, 999),
    "o2": (19.0, 21.0),  # % — 정상 중간값
    "lel": (0, 5),  # % — 폭발하한계 (임계치 표 별도 없음)
    "no2": (0.0, 2.9),
    "so2": (0.0, 1.9),
    "o3": (0.0, 0.059),
    "nh3": (0, 24),
    "voc": (0.0, 0.49),
}

# 위험 구간 생성 범위 (강제 이벤트 시 사용)
GAS_DANGER_RANGE = {
    "co": (200, 300),
    "h2s": (15, 50),
    "co2": (5000, 8000),
    "o2": (10.0, 15.0),  # % — 낮을수록 위험
    "lel": (10, 30),
    "no2": (5.0, 10.0),
    "so2": (5.0, 10.0),
    "o3": (0.12, 0.30),
    "nh3": (35, 70),
    "voc": (1.0, 2.0),
}


# ============================================================
# 상태 판단 함수
# ============================================================


def calculate_gas_status(gas_values: dict) -> str:
    """
    가스 측정값 딕셔너리를 받아 전체 상태를 판정한다.

    하나라도 '위험' 등급이면 즉시 danger 반환.
    하나라도 '주의' 등급이면 warning 반환.
    전체 정상이면 normal 반환.

    Args:
        gas_values: 가스 필드 딕셔너리 (co, h2s, co2, o2, lel, no2, so2, o3, nh3, voc)

    Returns:
        str: "normal" | "warning" | "danger"
    """
    overall_status = "normal"

    for gas, value in gas_values.items():
        if gas == "lel":
            # lel은 별도 임계치 기준 없음 — 상태 판단 제외
            continue

        thresholds = GAS_THRESHOLDS.get(gas)
        if thresholds is None:
            continue

        if gas == "o2":
            # O2는 낮을수록 위험 (범위 기준)
            if value < thresholds["warning_min"]:
                return "danger"
            elif value < thresholds["normal_min"] or value > thresholds["normal_max"]:
                overall_status = "warning"
        else:
            # 나머지는 높을수록 위험
            if value >= thresholds["warning_max"]:
                return "danger"
            elif value >= thresholds["normal_max"]:
                overall_status = "warning"

    return overall_status


# ============================================================
# 기기 정보 전송 데이터 생성 (부팅 시 1회)
# ============================================================


def generate_device_info() -> dict:
    """
    기기 정보 더미 데이터를 생성한다.

    프로토콜 원본 필드: device_id, device_name, software_version
    추가 필드: location (지오펜스 좌표 연산용, 고정값)

    sample:
        {
            "device_id": "63200c3afd12",
            "device_name": "63200c3afd12",
            "software_version": "1.0.1",
            "location": { "x": 140, "y": 160 }
        }

    Returns:
        dict: 기기 정보 데이터
    """
    return {
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
        "software_version": SOFTWARE_VERSION,
        "location": SENSOR_LOCATION,  # 지오펜스 좌표 (고정값)
    }


# ============================================================
# 기기 환경 데이터 전송 생성 (1초마다)
# ============================================================


def _pick_value(gas: str, is_danger_event: bool) -> float:
    """
    가스 종류와 이벤트 여부에 따라 랜덤 측정값을 반환한다.

    정수 범위는 randint, 소수 범위는 uniform을 사용한다.

    Args:
        gas: 가스 종류 키 (co, h2s, o2 등)
        is_danger_event: True이면 위험 구간에서 생성

    Returns:
        float | int: 생성된 측정값
    """
    range_map = GAS_DANGER_RANGE if is_danger_event else GAS_NORMAL_RANGE
    low, high = range_map[gas]
    if isinstance(low, float) or isinstance(high, float):
        return round(random.uniform(low, high), 2)
    return random.randint(int(low), int(high))


def generate_gas_data(is_danger_event: bool = False) -> dict:
    """
    기기 환경 센서 더미 데이터를 생성한다.

    프로토콜 원본 필드: device_id, o2, co, co2, h2s, lel
    확장 필드 (9종 전체): + no2, so2, o3, nh3, voc
    추가 필드: location (지오펜스 좌표), status (상태 판정값), timestamp

    sample:
        {
            "timestamp": "2026-04-21T10:00:00",
            "device_id": "63200c3afd12",
            "device_name": "63200c3afd12",
            "location": { "x": 140, "y": 160 },
            "o2": 20,
            "co": 12,
            "co2": 560,
            "h2s": 4,
            "lel": 2,
            "no2": 1.2,
            "so2": 0.8,
            "o3": 0.02,
            "nh3": 8,
            "voc": 0.3,
            "status": "normal"
        }

    Args:
        is_danger_event: True이면 위험 구간 값 강제 생성

    Returns:
        dict: 기기 환경 데이터
    """
    gas_values = {
        "o2": _pick_value("o2", is_danger_event),
        "co": _pick_value("co", is_danger_event),
        "co2": _pick_value("co2", is_danger_event),
        "h2s": _pick_value("h2s", is_danger_event),
        "lel": _pick_value("lel", is_danger_event),
        "no2": _pick_value("no2", is_danger_event),
        "so2": _pick_value("so2", is_danger_event),
        "o3": _pick_value("o3", is_danger_event),
        "nh3": _pick_value("nh3", is_danger_event),
        "voc": _pick_value("voc", is_danger_event),
    }

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
        "location": SENSOR_LOCATION,  # 지오펜스 좌표 (고정값)
        **gas_values,  # 가스 9종 + lel flat 구조
        "status": calculate_gas_status(gas_values),
    }


# ============================================================
# 전력 데이터 생성 (구현만 해두고, 현재 미전송)
# ============================================================


def generate_power_onoff_data() -> dict:
    """
    기기 ON/OFF 상태 더미 데이터를 생성한다.

    켜짐: 255 / 꺼짐: 0 (프로토콜 규정값)

    Returns:
        dict: 16채널 ON/OFF 상태 데이터
    """
    data = {"device_id": DEVICE_ID}
    for channel in POWER_CHANNELS:
        data[channel] = 255 if random.random() < 0.7 else 0
    return data


def generate_power_current_data() -> dict:
    """
    기기 전류 더미 데이터를 생성한다.

    단위: A / -1은 해당 포트 통신 불능 (프로토콜 규정)

    Returns:
        dict: 16채널 전류 데이터 (A)
    """
    data = {"device_id": DEVICE_ID}
    for channel in POWER_CHANNELS:
        data[channel] = random.randint(1, 30) if random.random() < 0.5 else 0
    return data


def generate_power_voltage_data() -> dict:
    """
    기기 전압 더미 데이터를 생성한다.

    단위: V / -1은 해당 포트 통신 불능 (프로토콜 규정)

    Returns:
        dict: 16채널 전압 데이터 (V)
    """
    data = {"device_id": DEVICE_ID}
    for channel in POWER_CHANNELS:
        data[channel] = random.randint(215, 225) if random.random() < 0.5 else 0
    return data


def generate_power_watt_data() -> dict:
    """
    기기 전력 더미 데이터를 생성한다.

    단위: W / -1은 해당 포트 통신 불능 (프로토콜 규정)

    Returns:
        dict: 16채널 전력 데이터 (W)
    """
    data = {"device_id": DEVICE_ID}
    for channel in POWER_CHANNELS:
        data[channel] = random.randint(50, 5000) if random.random() < 0.5 else 0
    return data


# ============================================================
# 전송 공통 함수
# ============================================================


def send_data(url: str, payload: dict, label: str) -> None:
    """
    지정한 FastAPI 엔드포인트로 JSON 데이터를 전송한다.

    Args:
        url: 전송 대상 FastAPI 엔드포인트 URL
        payload: 전송할 JSON 데이터 (dict)
        label: 로그 출력용 데이터 종류 레이블
    """
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=5,
        )
        logger.info(
            f"[{label}] 전송 완료 → HTTP {response.status_code} | "
            f"status={payload.get('status', '-')} | {payload}"
        )
    except requests.exceptions.ConnectionError:
        logger.error(
            f"[{label}] 전송 실패 → FastAPI 서버 연결 불가 (URL: {url}) | "
            f"서버가 실행 중인지 확인하세요."
        )
    except requests.exceptions.Timeout:
        logger.error(f"[{label}] 전송 실패 → 응답 시간 초과 (5초)")
    except Exception as e:
        logger.error(f"[{label}] 전송 실패 → {e}")


# ============================================================
# 메인 루프
# ============================================================


def run_gas_sender() -> None:
    """
    기기 정보를 1회 전송한 후, 기기 환경 데이터를 1초마다 FastAPI로 전송한다.

    전송 흐름:
      1. 기기 정보 (device info) → 1회 전송
      2. 기기 환경 데이터 (gas) → 1초마다 반복 전송

    Ctrl+C로 종료한다.
    """
    logger.info("=== 더미 데이터 전송 시작 ===")
    logger.info(f"위험 이벤트 발생 확률: {int(DANGER_EVENT_PROB * 100)}%")
    logger.info("종료하려면 Ctrl+C 를 누르세요.\n")

    # --- STEP 1. 기기 정보 1회 전송 (부팅 시 시뮬레이션) ---
    device_info = generate_device_info()
    send_data(FASTAPI_DEVICE_INFO_URL, device_info, "DEVICE_INFO")
    logger.info(f"기기 정보 전송 완료: {device_info}\n")

    # --- STEP 2. 기기 환경 데이터 반복 전송 ---
    logger.info(f"가스 환경 데이터 전송 시작 → {FASTAPI_GAS_URL}")

    while True:
        is_danger_event = random.random() < DANGER_EVENT_PROB
        gas_payload = generate_gas_data(is_danger_event=is_danger_event)
        send_data(FASTAPI_GAS_URL, gas_payload, "GAS")
        time.sleep(1)


# ============================================================
# 미사용: 전력 데이터 전송 루프 (추후 연동 시 활성화)
# ============================================================


def run_power_sender() -> None:
    """
    전력 데이터(ON/OFF, 전류, 전압, 전력)를 1분마다 FastAPI로 전송하는 루프.

    현재 미사용 상태.
    전력 장비 연동 시 run_gas_sender()와 함께 별도 스레드로 실행한다.
    TODO(재용): 전력 장비 연동 단계에서 활성화
    """
    logger.info("=== 전력 데이터 더미 전송 시작 ===")

    while True:
        send_data(FASTAPI_POWER_ONOFF_URL, generate_power_onoff_data(), "POWER_ONOFF")
        send_data(
            FASTAPI_POWER_CURRENT_URL, generate_power_current_data(), "POWER_CURRENT"
        )
        send_data(
            FASTAPI_POWER_VOLTAGE_URL, generate_power_voltage_data(), "POWER_VOLTAGE"
        )
        send_data(FASTAPI_POWER_WATT_URL, generate_power_watt_data(), "POWER_WATT")
        time.sleep(60)  # 전력 데이터는 1분에 한 번 전송


if __name__ == "__main__":
    # 현재는 가스 센서만 연동
    # 전력 데이터 연동 시: run_power_sender()를 별도 스레드로 추가
    run_gas_sender()
