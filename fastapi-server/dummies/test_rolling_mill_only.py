# dummies/test_rolling_mill_only.py — 압연기(channel 1 / slave01) 단독 테스트
#
# T1+T6 워딩 검증 전용. 다른 15채널은 정상값 (rated × 0.5) 고정, 압연기만
# 시나리오별 anomaly 값 주입 → 운영자가 압연기 알람만 격리해서 확인 가능.
#
# 사용:
#   uv run python -m dummies.test_rolling_mill_only [scenario]
#
# scenario: normal / overload / extreme (default: overload)
#   normal     — 정상값 (4500W ≈ rated×0.6) 30회 송출 → IF 윈도우 build + 정상화 토스트 확인
#   overload   — 정상 30회 → 스파이크 1회 (8500W ≈ rated×1.13) → IF/룰 발화
#   extreme    — 즉시 12000W (rated×1.6) 송출 → 룰 알람 + IF 동시 발화 가능
#
# Ctrl+C 로 중단.

import logging
import sys
import time
from datetime import datetime, timezone

import requests

from core.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

FASTAPI_BASE_URL = f"http://{settings.DUMMY_TARGET_HOST}:{settings.DUMMY_TARGET_PORT}"
FASTAPI_POWER_WATT_URL = f"{FASTAPI_BASE_URL}/api/power/watt"
FASTAPI_POWER_ONOFF_URL = f"{FASTAPI_BASE_URL}/api/power/onoff"

DEVICE_ID = "63200c3afd12"

# 16채널 정상 baseline (rated × 0.5 — 정격 절반 수준, 알람 트리거 안 함)
NORMAL_WATTS = {
    "slave01": 4500.0,  # 압연기 (rated 7500, 정상 ≈ 4500)
    "slave02": 1850.0,  # 송풍기 (rated 3700)
    "slave11": 2750.0,  # 집진기 (rated 5500)
    "slave12": 2000.0,
    "slave21": 1100.0,
    "slave22": 1850.0,
    "slave31": 750.0,
    "slave32": 2750.0,
    "slave41": 7500.0,
    "slave42": 3750.0,
    "slave51": 3750.0,
    "slave52": 1500.0,
    "slave61": 1500.0,
    "slave62": 2750.0,
    "slave71": 500.0,
    "slave72": 1100.0,
}

SCENARIO_WATT = {
    "normal": 4500.0,
    "overload": 8500.0,  # rated × 1.13 — IF anomaly + 룰 danger 둘 다 가능
    "extreme": 12000.0,  # rated × 1.6 — 룰 danger 확정 + IF 강한 anomaly
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _send_watt(slave01_value: float, anomaly: bool = False) -> None:
    payload = dict(NORMAL_WATTS)
    payload["slave01"] = slave01_value
    payload = {"device_id": DEVICE_ID, **payload}
    if anomaly:
        payload["anomaly_labels"] = {"1": "overload"}
    try:
        resp = requests.post(FASTAPI_POWER_WATT_URL, json=payload, timeout=5)
        logger.info(
            "[WATT] slave01=%s W HTTP %s anomaly=%s",
            slave01_value,
            resp.status_code,
            anomaly,
        )
    except Exception as exc:
        logger.error("전송 실패: %s", exc)


def _send_onoff() -> None:
    payload = {
        "device_id": DEVICE_ID,
        **{ch: 1 for ch in NORMAL_WATTS.keys()},
    }
    try:
        requests.post(FASTAPI_POWER_ONOFF_URL, json=payload, timeout=5)
    except Exception:
        pass


def run(scenario: str = "overload") -> None:
    if scenario not in SCENARIO_WATT:
        logger.error("scenario must be one of: %s", list(SCENARIO_WATT))
        sys.exit(1)

    interval = settings.DUMMY_SEND_INTERVAL_SEC
    logger.info(
        "=== 압연기 단독 테스트 시작 (scenario=%s, interval=%ds) ===",
        scenario,
        interval,
    )
    _send_onoff()

    if scenario == "extreme":
        # 즉시 스파이크 — IF 윈도우 빌드 전에도 룰 알람 발화 가능
        while True:
            _send_watt(SCENARIO_WATT["extreme"], anomaly=True)
            time.sleep(interval)
        return

    # normal / overload — 정상 30회로 IF 윈도우 build 후 anomaly 주입
    logger.info("[1/3] 정상값 30회 송출 — IF sliding window build...")
    for i in range(30):
        _send_watt(NORMAL_WATTS["slave01"])
        time.sleep(interval)

    if scenario == "normal":
        logger.info("[2/3] 정상값 유지 — 정상 복귀 토스트 확인용")
        while True:
            _send_watt(NORMAL_WATTS["slave01"])
            time.sleep(interval)

    # overload — anomaly 스파이크 시작
    logger.info("[2/3] overload 스파이크 시작 (%s W)", SCENARIO_WATT["overload"])
    while True:
        _send_watt(SCENARIO_WATT["overload"], anomaly=True)
        time.sleep(interval)


if __name__ == "__main__":
    scenario_arg = sys.argv[1] if len(sys.argv) > 1 else "overload"
    try:
        run(scenario_arg)
    except KeyboardInterrupt:
        logger.info("중단됨")
