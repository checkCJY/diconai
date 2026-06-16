# dummies/gas_dummy.py — 가스 센서 더미 데이터 전송 스크립트 (IF 학습 데이터용)
#
# 실제 에어위드 가스 센서 장비 대신 FastAPI 엔드포인트에 더미 데이터를 주기적으로 전송한다.
# 기동 시 /api/sensors/info 에 장비 식별 정보를 1회 전송하고,
# 이후 /api/sensors/gas 에 가스 측정값을 반복 전송한다.
#
# 상태머신(RAMP_UP/HOLD/RAMP_DOWN) + 가중치 random.choices + anomaly_type 페이로드
# 동봉으로 IF 가 "정상 → 사고 진입 → 회복" 의 연속적 변화를 학습할 수 있게 하고,
# DB 의 GasData.is_anomaly/anomaly_type 으로 학습/평가 데이터를 추출 가능하게 한다.
#
# 가스 vs 전력 차이:
# - 전력: 16채널 각자 독립 상태머신 (채널별 시나리오 다를 수 있음)
# - 가스: 9가스가 같은 상태머신 1개 공유 (시나리오 1개가 row 전체 = 9가스 동시 영향)
#
# 모드:
#   mixed       — 정상 90% + 가중치 시나리오 10% (IF 학습 데이터셋 생성)
#   normal/warning/danger — 전 가스 동일 레벨 강제 (UI/알람 테스트)
#   co_leak/h2s_leak/fire/chemical_spill — 단일 시나리오 강제 (격리 테스트)
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
from dummies._state_machine import (
    ChannelState,
    enter_scenario,
    maybe_trigger,
    step,
)

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
    "o3": (0.0, 0.05),
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
    "o3": (
        0.061,
        0.109,
    ),  # 0.119는 round(2) 후 0.12(danger 임계치)가 될 수 있어 0.109로 조정
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

# 시나리오 정의 — 실제 사고 유형별 가스 위험도 패턴.
# 각 시나리오는 {가스명: 레벨} 매핑 — 명시된 가스만 해당 레벨로, 나머지는 normal 로 샘플링.
#
# co_leak        : 일산화탄소 누출 (연소 부족/환기 불량)
#                  co↑(danger) + co2↑(warning, 산소소비) + o2↓(warning, 산소결핍)
# h2s_leak       : 황화수소 누출 (하수/화학약품)
#                  h2s↑(danger) + o2↓(warning) + so2↑(warning, h2s 산화부산물)
# fire           : 화재/폭발 전조 (lel 상승 + 연소가스)
#                  lel↑(danger) + co↑(warning) + co2↑(danger) + o2↓(danger) + voc↑(warning)
# chemical_spill : 유해화학물 다중 누출
#                  no2↑(danger) + so2↑(danger) + nh3↑(danger) + o3↑(warning) + voc↑(danger)
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
    # 이성현 추가 — C. 산소 농도 저하 시나리오 (O2만 서서히 내려가는 밀폐공간 질식 패턴)
    "o2_depletion": {
        "o2": "danger",
    },
    # 이성현 추가 — H. 센서 오류/통신 불량 시나리오 (전 가스값 0 고정, 레벨 정의 없음)
    # _build_gas_values 에서 별도 분기 처리 — SCENARIOS 에는 빈 dict 로 등록
    "sensor_fault": {},
}

_SCENARIO_NAMES = list(SCENARIOS.keys())

# 상태머신 파라미터 (시나리오별)
# ramp_up   : 정상→사고 점진 진입 틱 수
# hold      : 사고 상태 유지 틱 수
# ramp_down : 사고→정상 점진 회복 틱 수
# 1틱 = DUMMY_SEND_INTERVAL_SEC 초 (기본 1초)
SCENARIO_PATTERNS: dict[str, dict[str, int]] = {
    # co_leak 만 env override 지원 — 시연 시 격상 흐름 가시화용 (settings 기본 5/30/5).
    "co_leak": {
        "ramp_up": settings.DEMO_CO_LEAK_RAMP_UP_TICKS,
        "hold": settings.DEMO_CO_LEAK_HOLD_TICKS,
        "ramp_down": settings.DEMO_CO_LEAK_RAMP_DOWN_TICKS,
    },
    "h2s_leak": {"ramp_up": 5, "hold": 30, "ramp_down": 5},
    "fire": {"ramp_up": 3, "hold": 20, "ramp_down": 5},  # 화재는 더 빠른 진입
    "chemical_spill": {"ramp_up": 5, "hold": 30, "ramp_down": 5},
    # 이성현 추가 — C. 산소 농도 저하는 서서히 진행되므로 ramp_up/ramp_down 길게 설정
    "o2_depletion": {"ramp_up": 10, "hold": 40, "ramp_down": 10},
    # 이성현 추가 — H. 센서 오류는 갑작스럽게 발생하므로 ramp_up/ramp_down 최소화
    "sensor_fault": {"ramp_up": 1, "hold": 10, "ramp_down": 1},
}

# 가중치 — 발생 빈도(가스 사고 통계 기반 초기값, 운영 데이터 축적 후 보정)
# 4종 모두 유사 빈도 (전력 overload 처럼 dominant 시나리오 없음)
# 이성현 추가 — o2_depletion 가중치 3 추가
SCENARIO_WEIGHTS = [
    6,
    4,
    4,
    4,
    3,
    2,
]  # co_leak / h2s_leak / fire / chemical_spill / o2_depletion / sensor_fault
HOLD_TICKS_BY_SCENARIO = {k: v["hold"] for k, v in SCENARIO_PATTERNS.items()}

# mixed 모드에서 매 틱마다 NORMAL 상태일 때 시나리오 진입할 확률.
# 평균 1 / MIXED_TRIGGER_PROBABILITY 틱마다 1건 시나리오 발생.
# DANGER_EVENT_PROB(.env)을 그대로 재사용 — 운영자가 환경변수로 조정 가능.
MIXED_TRIGGER_PROBABILITY = DANGER_EVENT_PROB

# 가스는 row=시점 단위 시나리오라 9가스가 같은 상태머신 1개 공유.
_gas_state = ChannelState()


def _pick_value(gas: str, level: str) -> float | int:
    """가스 종류와 위험도 라벨에 따라 해당 범위 내 랜덤값을 반환한다."""
    low, high = _RANGE_BY_LEVEL[level][gas]
    if isinstance(low, float) or isinstance(high, float):
        return round(random.uniform(low, high), 2)
    return random.randint(int(low), int(high))


# FIXED 모드 (전 가스 동일 레벨 강제) 식별용
FIXED_LEVELS = {"normal", "warning", "danger"}


def _apply_mode(mode: str) -> None:
    """매 틱 시작 시 호출. 상태머신 트리거 또는 강제 진입."""
    if mode == "mixed":
        maybe_trigger(
            _gas_state,
            probability=MIXED_TRIGGER_PROBABILITY,
            scenarios=_SCENARIO_NAMES,
            weights=SCENARIO_WEIGHTS,
            hold_ticks_by_scenario=HOLD_TICKS_BY_SCENARIO,
            ramp_up_ticks=5,
            ramp_down_ticks=5,
        )
        return
    if mode in SCENARIO_PATTERNS:
        pattern = SCENARIO_PATTERNS[mode]
        enter_scenario(
            _gas_state,
            scenario=mode,
            ramp_up_ticks=pattern["ramp_up"],
            hold_ticks=pattern["hold"],
            ramp_down_ticks=pattern["ramp_down"],
        )
        return
    # FIXED_LEVELS 또는 알 수 없는 모드 — 상태머신 미사용, _build_gas_values 에서 fallback 처리.


def _build_gas_values(mode: str) -> tuple[dict[str, float | int], str | None]:
    """상태머신 진행 후 가스값 9종과 anomaly_type(시나리오명 or None)을 반환한다.

    상태머신 weight 에 따라 normal_pick 과 scenario_pick 을 선형 보간 (mix).
    weight=0 → 완전 정상, weight=1 → 완전 사고 (HOLD 구간).
    """
    _apply_mode(mode)

    # FIXED 모드 — 전 가스 동일 레벨, 라벨 없음
    if mode in FIXED_LEVELS:
        return (
            {gas: _pick_value(gas, mode) for gas in GAS_NORMAL_RANGE},
            None,
        )

    # 상태머신 진행
    out = step(_gas_state)

    if not out.is_anomaly:
        return (
            {gas: _pick_value(gas, "normal") for gas in GAS_NORMAL_RANGE},
            None,
        )

    # 시나리오 진행 중 — normal_pick 과 scenario_pick 을 weight 로 가중평균
    scenario = out.anomaly_type or "co_leak"
    # 이성현 추가 — H. 센서 오류: 상태머신 보간 없이 전 가스값 0.0 고정 반환
    if scenario == "sensor_fault":
        return (
            {gas: 0.0 for gas in GAS_NORMAL_RANGE},
            "sensor_fault",
        )
    scenario_levels = SCENARIOS[scenario]
    weight = out.scenario_weight
    gas_values: dict[str, float | int] = {}
    for gas in GAS_NORMAL_RANGE:
        # 시연 시 RAMP_UP/RAMP_DOWN 동안 normal_pick 의 random noise 가 mix 값을
        # 임계 아래로 끌어내려 fire_clear → event RESOLVED → 격상 시 새 event_id
        # 가 발급되는 race 발생. 해결: normal range mid 가 아닌 normal_low 부터
        # scenario range mid 까지 weight 선형 보간 + ±15% noise.
        # → 단조 trend 보장 (event 격상 가시화) + IF 학습 시점의 noisy mix() 분포에
        #   feature(std/diff/arima_resid) 근사 → IF 가 anomaly 로 인식 (pred=-1).
        # → 혹시 발생할 임계 cross 는 C 패치 (partial skip) 가 흡수.
        normal_low = float(GAS_NORMAL_RANGE[gas][0])
        scenario_level = scenario_levels.get(gas, "normal")
        sc_low, sc_high = _RANGE_BY_LEVEL[scenario_level][gas]
        scenario_mid = (float(sc_low) + float(sc_high)) / 2
        v = normal_low + (scenario_mid - normal_low) * weight
        if weight >= 1.0:
            # HOLD 동안 큰 진폭 noise — IF feature (std/diff/arima_resid) 가 학습
            # 시점의 noisy mix() 분포에 근사 → IF score 음수로 끌어내려 pred=-1 유도.
            v *= random.uniform(0.6, 1.4)
        else:
            # RAMP_UP/RAMP_DOWN 동안 작은 noise — 단조 trend 보장 (격상 가시화)
            # + 시연 화면이 너무 인공적이지 않도록 ±5% 자연스러움.
            v *= random.uniform(0.95, 1.05)
        gas_values[gas] = round(v, 2)
    return gas_values, scenario


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

    상태머신 기반 시계열 자기상관 + anomaly_type 페이로드 동봉.
        - mixed: 가중치 random.choices 로 시나리오 진입 (정상/사고 자연스러운 전이)
        - 단일 시나리오 (co_leak/h2s_leak/fire/chemical_spill): 강제 진입
        - fixed (normal/warning/danger): 상태머신 미사용, 전 가스 동일 레벨
    """
    mode = get_scenario_mode()
    gas_values, anomaly_type = _build_gas_values(mode)
    payload: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
        "location": SENSOR_LOCATION,
        **gas_values,
        "status": calculate_gas_status(gas_values),
    }
    if anomaly_type is not None:
        payload["anomaly_type"] = anomaly_type
    return payload


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

    장비 정보를 1회 전송한 뒤 DUMMY_SEND_INTERVAL_SEC 주기로 가스 데이터를 반복 전송한다.
    상태머신 + 가중치 + anomaly_type 동봉 (IF 학습용).
    """
    logger.info(
        "=== 가스 더미 v3 시작 (주기: %ds | 트리거 확률: %d%% | 시나리오: %s | 가중치: %s) ===",
        settings.DUMMY_SEND_INTERVAL_SEC,
        int(MIXED_TRIGGER_PROBABILITY * 100),
        ", ".join(_SCENARIO_NAMES),
        SCENARIO_WEIGHTS,
    )
    send_data(FASTAPI_DEVICE_INFO_URL, generate_device_info(), "DEVICE_INFO")
    logger.info("가스 데이터 전송 시작 → %s", FASTAPI_GAS_URL)
    while True:
        payload = generate_gas_data()
        send_data(FASTAPI_GAS_URL, payload, "GAS")
        if payload.get("anomaly_type"):
            logger.info("[TICK] scenario=%s", payload["anomaly_type"])
        time.sleep(settings.DUMMY_SEND_INTERVAL_SEC)


if __name__ == "__main__":
    run()
