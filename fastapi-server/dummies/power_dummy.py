# dummies/power_dummy.py — 전력 센서 더미 데이터 전송 스크립트 (v3, IF 학습 데이터용)
#
# 실제 전력 센서 장비 대신 FastAPI 전력 엔드포인트에 더미 데이터를 주기적으로 전송한다.
# 한 루프에서 16채널의 (W, A, V) 값을 한 번에 계산하고 onoff → current → voltage → watt
# 순으로 4개 엔드포인트에 송신한다.
#
# [v3 변경 — IF 학습 데이터 품질 확보]
# v2: random.randint 균등 분포 + 시계열 자기상관 없음 → IF 학습 부적합
# v3: 채널 정격 기반 + 시간대별 base_load + 시나리오 5종(가중치) + 상태머신(RAMP/HOLD/DOWN)
#     + 채널별 is_anomaly/anomaly_type 라벨 페이로드 동봉
#
# 모드:
#   mixed       — 정상 90% + 가중치 적용 시나리오 10% (IF 학습 데이터셋 생성)
#   normal/warning/danger — 전 채널 동일 레벨 (UI/알람 테스트)
#   overload/voltage_drop/phase_loss/degradation/night_abnormal/motor_stuck
#               — 단일 시나리오 강제 (격리 테스트). W0 에서 spike 제거,
#                 night_abnormal/motor_stuck 신규. dummy 는 시각 게이트 없음 —
#                 night_abnormal 의 "야간 시각" 판정은 W3 추론 측에서 처리
#                 (measured_at hour 분기). dummy 책임 = 데이터 생성만.
#
# 실행: python -m dummies.power_dummy

import logging
import random
import time
from datetime import datetime, timezone

import requests

from core.config import settings
from dummies._scenario import get_scenario_mode

# [L-6] SLAVE_KEYS 는 power/schemas/power.py 가 단일 공급원 — 여기서 import 해 중복 제거.
from power.schemas.power import SLAVE_KEYS
from dummies._state_machine import (
    ChannelState,
    enter_scenario,
    maybe_trigger,
    mix,
    step,
)

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

# [L-6] power/schemas/power.py 의 SLAVE_KEYS 가 단일 공급원이므로 별도 정의 제거.
POWER_CHANNELS = SLAVE_KEYS

# ---------------------------------------------------------------------------
# 채널 정격 — drf-server/apps/facilities/migrations/0017_seed_power_channel_meta.py 와 동일.
# 시드와 갈라지지 않게 변경 시 양쪽 동시 수정 필수.
# ---------------------------------------------------------------------------
CHANNEL_RATED: dict[int, dict[str, float]] = {
    1: {"w": 7500, "a": 30, "v": 380},
    2: {"w": 3700, "a": 15, "v": 380},
    3: {"w": 5500, "a": 22, "v": 380},
    4: {"w": 4000, "a": 16, "v": 380},
    5: {"w": 2200, "a": 10, "v": 380},
    6: {"w": 3700, "a": 15, "v": 380},
    7: {"w": 1500, "a": 7, "v": 380},
    8: {"w": 5500, "a": 22, "v": 380},
    9: {"w": 15000, "a": 50, "v": 380},
    10: {"w": 7500, "a": 30, "v": 380},
    11: {"w": 7500, "a": 30, "v": 380},
    12: {"w": 3000, "a": 14, "v": 380},
    13: {"w": 3000, "a": 14, "v": 380},
    14: {"w": 5500, "a": 22, "v": 380},
    15: {"w": 1000, "a": 5, "v": 220},
    16: {"w": 2200, "a": 10, "v": 380},
}

# 모터성 채널(과부하·결상·스파이크·열화 시나리오 후보) vs 분전반/조명/예비.
MOTOR_CHANNELS = [1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14]
LIGHTING_CHANNELS = [15]
PANEL_CHANNELS = [9, 10, 11, 16]

# 시연용 — single 시나리오의 random.choice 풀.
# anomaly_inference._INFERENCE_ENABLED_CHANNELS 와 동기화 필수.
AI_DEMO_CHANNELS = [1, 9, 14, 15]


# ---------------------------------------------------------------------------
# 시간대별 기저 부하 비율 (정격 대비). 평일 공장 가동 패턴 가정.
# ---------------------------------------------------------------------------
def base_load_ratio(hour: int, ch: int) -> float:
    """채널 종류·시간대 기반 기저 부하 비율 (정격 대비, 0.0~1.0).

    T4 D2 시연 검증 (2026-05-20) — 이전 0.60/0.70 + gauss noise(0.05) 가 정적
    80% 임계 부근에 자주 도달해 시나리오 모드 무관 자연 발화 다발. baseline 을
    0.50/0.55 로 낮춰 80% 와 충분 거리 확보 → T4 cover 시연이 noise 에 묻히지
    않도록.
    """
    if ch in LIGHTING_CHANNELS:
        return 0.4  # 조명은 시간대 무관 일정
    if ch in PANEL_CHANNELS:
        return 0.5  # 분전반/메인은 평탄
    # 모터 채널 — 작업 시간대 기반
    if 8 <= hour < 12:
        return 0.50
    if 13 <= hour < 18:
        return 0.55
    if 19 <= hour < 22:
        return 0.30
    return 0.15  # 야간/새벽


# ---------------------------------------------------------------------------
# 시나리오 6종 — (정격 대비 배수 W/A/V) + 상태머신 파라미터
# W0 변경 (skill/plan/power-ai-un-downgrade-phase2-apply.md §3):
#   - spike 제거 — 1틱 단발 급등은 정적 룰 임계치가 즉시 잡음 (ML 영역 아님)
#   - night_abnormal 신규 (P0) — ARIMA seasonal/baseline 일탈 시연 (야간 시간대 한정)
#   - motor_stuck 신규 (P1) — IF 다축 상관 학습 신호 (W↓+A↓ 동시 + V 유지)
# ---------------------------------------------------------------------------
SCENARIO_PATTERNS: dict[str, dict] = {
    "overload": {  # P0 — 룰 + IF + ARIMA 모두 동의 (시연 핵심)
        "w_factor": 1.10,
        "a_factor": 1.10,
        "v_factor": 0.93,
        "ramp_up": 5,
        "hold": 60,
        "ramp_down": 10,
    },
    "voltage_drop": {  # 보조 — multi-channel 시나리오 (Phase 3 다채널 학습 가치)
        "w_factor": 0.85,
        "a_factor": 1.10,
        "v_factor": 0.88,
        "ramp_up": 3,
        "hold": 30,
        "ramp_down": 5,
        "multi": True,  # 전 채널에 적용
    },
    "phase_loss": {  # 보조 — 3상 결상 도메인 사고 패턴 (95% drop = 정적 임계치)
        "w_factor": 0.05,
        "a_factor": 0.05,
        "v_factor": 0.05,
        "ramp_up": 2,
        "hold": 30,
        "ramp_down": 5,
    },
    "degradation": {  # P0 — ARIMA trend break 시연 가치
        "w_factor": 1.05,
        "a_factor": 1.05,
        "v_factor": 1.00,
        "ramp_up": 60,
        "hold": 30,
        "ramp_down": 5,
    },
    "night_abnormal": {  # P0 신규 — "야간 가동" 패턴 데이터 (시각 판정은 W3 추론 측)
        "w_factor": 3.00,  # 정격 300% — 시각 무관 큰 anomaly. W3 에서 야간 시각 가중치 추가
        "a_factor": 3.00,
        "v_factor": 1.00,
        "ramp_up": 5,
        "hold": 120,  # 야간 시간대 충분히 유지
        "ramp_down": 10,
    },
    "motor_stuck": {  # P1 신규 — 회전 정지 (W·A 동시 ↓, V 유지)
        "w_factor": 0.10,
        "a_factor": 0.10,
        "v_factor": 1.00,
        "ramp_up": 1,  # 급정지
        "hold": 60,
        "ramp_down": 1,
    },
}

SCENARIO_NAMES = list(SCENARIO_PATTERNS.keys())
# W0 가중치 재분배 — P0 70 / P1 15 / 보조 15 (합 100).
# 순서는 SCENARIO_PATTERNS dict 정의 순과 동일 (Python 3.7+ 정렬 보장):
#   overload=30, voltage_drop=8, phase_loss=7, degradation=20, night_abnormal=20, motor_stuck=15
SCENARIO_WEIGHTS = [30, 8, 7, 20, 20, 15]
HOLD_TICKS_BY_SCENARIO = {k: v["hold"] for k, v in SCENARIO_PATTERNS.items()}

# ---------------------------------------------------------------------------
# 시나리오 트리거 확률 — mixed 모드에서 매 틱마다 NORMAL 채널이 진입할 확률
# 채널 16개 × probability 가 평균 동시 진행 시나리오 수.
# 0.005 = 16채널 × 0.005 = 0.08 → 평균 12.5틱당 1건 시나리오 진입
# ---------------------------------------------------------------------------
MIXED_TRIGGER_PROBABILITY = 0.005


# ---------------------------------------------------------------------------
# 채널별 상태 — 프로세스 메모리 보존
# ---------------------------------------------------------------------------
_channel_states: dict[int, ChannelState] = {ch: ChannelState() for ch in range(1, 17)}


def _gauss_factor(stddev: float = 0.05) -> float:
    """1.0 주변의 가우스 노이즈 (clamp [0.5, 1.5])."""
    return max(0.5, min(1.5, random.gauss(1.0, stddev)))


def _compute_channel_tick(
    ch: int, hour: int
) -> tuple[float, float, float, bool, bool, str | None]:
    """채널 1개의 (W, A, V, onoff, is_anomaly, anomaly_type) 를 1틱 계산."""
    rated = CHANNEL_RATED[ch]
    base_ratio = base_load_ratio(hour, ch)

    # 정상값 — 정격 × base_ratio × 노이즈
    normal_w = rated["w"] * base_ratio * _gauss_factor(0.05)
    normal_a = rated["a"] * base_ratio * _gauss_factor(0.05)
    normal_v = rated["v"] * _gauss_factor(0.01)

    cs = _channel_states[ch]
    out = step(cs)
    onoff = base_ratio > 0.2  # 야간 저부하 시 일부 채널 OFF로 표현

    if not out.is_anomaly:
        return (
            round(normal_w, 1),
            round(normal_a, 2),
            round(normal_v, 1),
            onoff,
            False,
            None,
        )

    scenario = out.anomaly_type or "overload"
    pattern = SCENARIO_PATTERNS[scenario]

    # 시나리오 적용값 — 정격 × factor × 약한 노이즈
    scenario_w = rated["w"] * pattern["w_factor"] * _gauss_factor(0.03)
    scenario_a = rated["a"] * pattern["a_factor"] * _gauss_factor(0.03)
    scenario_v = rated["v"] * pattern["v_factor"] * _gauss_factor(0.01)

    weight = out.scenario_weight
    w = mix(normal_w, scenario_w, weight)
    a = mix(normal_a, scenario_a, weight)
    v = mix(normal_v, scenario_v, weight)
    return round(w, 1), round(a, 2), round(v, 1), True, True, scenario


# ---------------------------------------------------------------------------
# 모드별 사전 처리 — fixed/단일 시나리오 모드 진입 강제
# ---------------------------------------------------------------------------
FIXED_LEVELS = {"normal", "warning", "danger"}


def _apply_mode(mode: str) -> None:
    """매 틱 시작 시 호출. 시나리오 트리거 또는 강제 진입.

    dummy 는 시각 게이트 없음 — night_abnormal 의 "야간 시각" 판정은 W3
    추론 측 책임 (measured_at hour 분기). 데이터는 시각 무관 항상 생성.
    """
    if mode == "mixed":
        for ch in range(1, 17):
            maybe_trigger(
                _channel_states[ch],
                probability=MIXED_TRIGGER_PROBABILITY,
                scenarios=SCENARIO_NAMES,
                weights=SCENARIO_WEIGHTS,
                hold_ticks_by_scenario=HOLD_TICKS_BY_SCENARIO,
                ramp_up_ticks=5,
                ramp_down_ticks=10,
            )
        return

    if mode in SCENARIO_PATTERNS:
        # 단일 시나리오 강제 — multi 면 전 채널, 아니면 AI 학습 채널 중 1개.
        pattern = SCENARIO_PATTERNS[mode]
        targets = (
            list(range(1, 17))
            if pattern.get("multi")
            else [random.choice(AI_DEMO_CHANNELS)]
        )
        for ch in targets:
            enter_scenario(
                _channel_states[ch],
                scenario=mode,
                ramp_up_ticks=pattern["ramp_up"],
                hold_ticks=pattern["hold"],
                ramp_down_ticks=pattern["ramp_down"],
            )
        return

    # FIXED_LEVELS — 상태머신 사용 안 함. _compute_channel_tick 는 normal 경로로 동작.
    # 알람 색상 테스트는 별도 분기에서 처리.


def _fixed_level_value(ch: int, level: str) -> tuple[float, float, float]:
    """fixed 모드 (normal/warning/danger) — 정격 대비 % 비율로 즉시 산출."""
    rated = CHANNEL_RATED[ch]
    if level == "normal":
        ratio_w = ratio_a = 0.5
        ratio_v = 1.0
    elif level == "warning":
        ratio_w = ratio_a = 0.85  # 80% 이상
        ratio_v = 0.93  # 95% 이하 (양방향 임계의 저전압 경계 진입)
    else:  # danger
        ratio_w = ratio_a = 1.05  # 100% 이상
        ratio_v = 0.88  # 90% 이하
    w = rated["w"] * ratio_w * _gauss_factor(0.02)
    a = rated["a"] * ratio_a * _gauss_factor(0.02)
    v = rated["v"] * ratio_v * _gauss_factor(0.005)
    return round(w, 1), round(a, 2), round(v, 1)


# ---------------------------------------------------------------------------
# 페이로드 빌더 — 매 틱마다 한 번 계산 후 4개 페이로드에 분배
# ---------------------------------------------------------------------------
def _build_tick() -> dict:
    """현재 틱의 채널별 (W, A, V, onoff, anomaly) 를 계산해 4개 페이로드를 한 번에 반환."""
    mode = get_scenario_mode()
    _apply_mode(mode)
    hour = datetime.now(timezone.utc).hour

    onoff_payload: dict = {"device_id": DEVICE_ID}
    current_payload: dict = {"device_id": DEVICE_ID}
    voltage_payload: dict = {"device_id": DEVICE_ID}
    watt_payload: dict = {"device_id": DEVICE_ID}
    anomaly_labels: dict[str, str] = {}

    for ch_idx, slave_key in enumerate(POWER_CHANNELS, start=1):
        if mode in FIXED_LEVELS:
            w, a, v = _fixed_level_value(ch_idx, mode)
            onoff = True
            is_anom = False
            anom_type = None
        else:
            w, a, v, onoff, is_anom, anom_type = _compute_channel_tick(ch_idx, hour)

        onoff_payload[slave_key] = 255 if onoff else 0
        current_payload[slave_key] = a
        voltage_payload[slave_key] = v
        watt_payload[slave_key] = w
        if is_anom and anom_type:
            anomaly_labels[str(ch_idx)] = anom_type

    if anomaly_labels:
        current_payload["anomaly_labels"] = anomaly_labels
        voltage_payload["anomaly_labels"] = anomaly_labels
        watt_payload["anomaly_labels"] = anomaly_labels

    return {
        "onoff": onoff_payload,
        "current": current_payload,
        "voltage": voltage_payload,
        "watt": watt_payload,
        "mode": mode,
        "anomaly_count": len(anomaly_labels),
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
        logger.info("[%s] HTTP %s", label, response.status_code)
    except requests.exceptions.ConnectionError:
        logger.error("[%s] 연결 실패 (URL: %s)", label, url)
    except requests.exceptions.Timeout:
        logger.error("[%s] 응답 시간 초과", label)
    except Exception as exc:
        logger.error("[%s] 전송 실패 — %s", label, exc)


def run() -> None:
    """더미 전송 루프를 시작한다.

    DUMMY_SEND_INTERVAL_SEC 주기로 한 틱의 16채널 (W,A,V) 를 계산한 뒤
    onoff → current → voltage → watt 4종 엔드포인트에 송신한다.
    """
    interval = settings.DUMMY_SEND_INTERVAL_SEC
    logger.info(
        "=== 전력 더미 v3 시작 (주기: %ds | 시나리오: %s | 가중치: %s) ===",
        interval,
        ", ".join(SCENARIO_NAMES),
        SCENARIO_WEIGHTS,
    )
    while True:
        tick = _build_tick()
        send_data(FASTAPI_POWER_ONOFF_URL, tick["onoff"], "POWER_ONOFF")
        send_data(FASTAPI_POWER_CURRENT_URL, tick["current"], "POWER_CURRENT")
        send_data(FASTAPI_POWER_VOLTAGE_URL, tick["voltage"], "POWER_VOLTAGE")
        send_data(FASTAPI_POWER_WATT_URL, tick["watt"], "POWER_WATT")
        if tick["anomaly_count"]:
            logger.info(
                "[TICK] mode=%s anomaly_channels=%d",
                tick["mode"],
                tick["anomaly_count"],
            )
        time.sleep(interval)


if __name__ == "__main__":
    run()
