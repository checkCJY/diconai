# power/services/power_service.py — 전력 데이터 처리 서비스
#
# 전력 센서 수신 데이터와 관련된 비즈니스 로직을 담당한다.
#   - DRF 비동기 전송 (BackgroundTask용 fire-and-forget 패턴)
#   - power_latest 공유 상태 갱신
#   - 채널 데이터를 equipment[] 형태로 조립해 WebSocket 브로드캐스트에 제공
#   - 채널 라벨·정격은 channel_meta_cache(DRF PowerDevice.channel_meta)에서 조회
#   - [트랙 1 v2] IF 추론 + combine_risk + push_alarm (process_anomaly_inference)
import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import numpy as np
from fastapi import HTTPException

from ai.risk_combine import combine_risk_5axis
from ai.router import (
    _arima_forecast,
    _build_feature_row,
    _get_or_load,
    _get_or_load_arima,
)
from core.power_thresholds import POWER_THRESHOLDS
from power.services.change_point_service import detect_change_point
from power.services.channel_meta_cache import get_channel_entry
from power.services.quality_guard import classify_sensor_status, is_inference_stuck
from power.services.threshold_eval import calculate_power_risk
from core.metrics import AI_INFERENCE_DURATION, AI_INFERENCE_FAILED_TOTAL
from services.anomaly_alarm import forward_inference_e2e
from services.drf_client import post_to_drf
from websocket.state import power_latest

logger = logging.getLogger(__name__)

# IF 추론용 in-memory 윈도우 — (channel, data_type) 별 deque(maxlen=window).
# 가스 _co_window 패턴을 power 다채널·다측정으로 확장. fastapi 재시작 시 초기화 (무상태).
_INFERENCE_WINDOW = 30
_power_windows: dict[tuple[int, str], deque] = defaultdict(
    lambda: deque(maxlen=_INFERENCE_WINDOW)
)

# combined_risk → AlarmPayload.risk_level (RiskLevel) 매핑.
# CAUTION/PREDICT_WARN 둘 다 RiskLevel.WARNING 으로 (RiskLevel 3단계라 합칠 수밖에).
# UI 에서 더 풍부한 구분은 C8 에서 AlarmPayload 에 combined_risk 필드 추가 후 가능.
_COMBINED_TO_RISK_LEVEL = {
    "normal": "normal",
    "caution": "warning",
    "predict_warn": "warning",
    "danger": "danger",
}
_FIRE_LEVELS = {"caution", "predict_warn", "danger"}

# 본 sprint active 모델은 (device_1, ch1, watt) 한 채널만 학습됨.
# 다른 채널은 학습 분포 안 맞아 false positive ↑ → §3 multi-channel sprint 까지 비활성.
_INFERENCE_ENABLED_CHANNELS: set[tuple[int, str]] = {(1, "watt")}

# 알람 발화 rate limit — 같은 sensor_identifier 60초당 1회.
# 폭주 방지 (overload HOLD 60틱 동안 매 추론 push_alarm → 브라우저 폭주 차단).
# rate limit 은 push_alarm 에만 적용. MLAnomalyResult forward 는 매번 (운영 추적 유지).
# severity escalation bypass (caution → danger 격상 시 즉시 발화) 는 planB followups.
_last_fired_at: dict[str, float] = {}
RATE_LIMIT_SEC = 60

DRF_POWER_EVENT_PATH = "/api/monitoring/power/event/"
DRF_POWER_DATA_PATH = "/api/monitoring/power/data/"

# W3.2 — night_abnormal 시각 분기 (dummy 는 시각 무관 데이터 생성, 추론 측이 판정).
# measured_at 의 KST hour 가 야간(22~05) + watt 가 야간 baseline 초과 시
# combined_risk 한 단계 격상. 임계치 = 정격 × NIGHT_THRESHOLD_RATIO (휴리스틱,
# 향후 자동화 옵션: SARIMAX seasonal / IF hour 피처 / 시각별 동적 임계치 — 필수 아님).
_KST_OFFSET_HOURS = 9
_NIGHT_GATE_KST = (22, 5)  # 22~익일 05 KST
_NIGHT_THRESHOLD_RATIO = 0.30  # 야간 base 0.15 의 2배 = 정격 30%
_NIGHT_ESCALATION = {
    "normal": "caution",
    "caution": "warning",
    "predict_warn": "warning",
}


def _zscore_check(
    window: deque, value: float, threshold: float = 3.0
) -> tuple[bool, float]:
    """Z-score 기반 이상 판정 (STEP D / plan §D2 — power-zscore-changepoint-apply).

    Sliding Window 의 mean/std 계산 후 |z| >= threshold 면 ANOMALY_WARNING.
    EPS=1e-9 로 std=0 인 분모 폭발 방지. window 길이가 _INFERENCE_WINDOW 미만이면
    (False, 0.0) (초반 통계 불안정 — STEP 1 의 min_periods 안전장치 패턴).

    Args:
        window: 최근 N개 값 deque (`_power_windows[(channel,data_type)]`).
                현재 value 가 이미 append 된 상태로 전달되어도 무방 — pandas rolling
                패턴과 동일하게 현재값 포함 mean/std 사용 (N=30 에서 1/N 영향 미미).
        value: 현재 측정값.
        threshold: Z-score 임계 (기본 3.0 — STEP 1 권고 3σ. 시연 후 튜닝).

    Returns:
        (is_anomaly, z) — is_anomaly 는 |z| >= threshold, z 는 실제 |z| 값 (로깅용).
        코드리뷰 2026-05-19 §3.1 — Z-score 발화 시점 가시성 보강.
    """
    if len(window) < _INFERENCE_WINDOW:
        return False, 0.0
    arr = np.array(window, dtype=float)
    mean = arr.mean()
    std = arr.std()
    z = abs(value - mean) / (std + 1e-9)
    return bool(z >= threshold), float(z)


def _is_night_kst_iso(measured_at_iso: str) -> bool:
    """ISO 8601 measured_at 의 KST hour 가 야간 시간대(22~05)에 속하는지."""
    try:
        dt = datetime.fromisoformat(measured_at_iso)
    except (ValueError, TypeError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc_hour = dt.astimezone(timezone.utc).hour
    kst_hour = (utc_hour + _KST_OFFSET_HOURS) % 24
    start, end = _NIGHT_GATE_KST
    if start <= end:
        return start <= kst_hour < end
    return kst_hour >= start or kst_hour < end


# 페이로드 표시용 정격 % 임계치 (DRF facilities.Threshold "power_facility_default"와 동일)
# 실제 알람 트리거는 DRF가 단일 진실 공급원. 본 모듈은 대시보드 색상 표시만 담당.
_PCT_THRESHOLDS = {
    "watt": {"warning": 80, "danger": 100, "bidirectional": False},
    "current": {"warning": 80, "danger": 100, "bidirectional": False},
    "voltage": {
        "warning_low": 95,
        "warning_high": 105,
        "danger_low": 90,
        "danger_high": 110,
        "bidirectional": True,
    },
}

_AXIS_BY_KEY = {"watt": "rated_w", "current": "rated_a", "voltage": "rated_v"}


def now_utc_iso() -> str:
    """현재 UTC 시각을 ISO 8601 문자열로 반환한다."""
    return datetime.now(timezone.utc).isoformat()


async def post_power_to_drf(path: str, payload: dict) -> None:
    """전력 데이터를 DRF에 비동기 fire-and-forget 전송.

    BackgroundTask에서 실행되므로 실패해도 WebSocket 흐름을 블로킹하지 않는다.
    실패는 services.drf_client가 logger.warning/error로 기록한다.
    """
    await post_to_drf(path, payload, raise_on_error=False, log_category="power_service")


async def process_anomaly_inference(
    device_id: str | None,
    channel_values: dict,
    data_type: str,
    measured_at: str,
    ingress_ts: float | None = None,
) -> None:
    """[트랙 1 v2] IF 추론 + combine_risk + push_alarm + DRF MLAnomalyResult forward.

    ch1·watt 등 _INFERENCE_ENABLED_CHANNELS 에 포함된 (channel, data_type) 만 추론.
    윈도우 누적 < _INFERENCE_WINDOW 면 skip. push_alarm 은 발화 levels 일 때만,
    MLAnomalyResult forward 는 추론 매번 (운영 추적용). 모든 외부 호출 silent fail —
    DRF 저장 흐름과 fastapi 응답 시간에 영향 없음.

    ingress_ts — 핸들러 진입 시각. AI 알람 push_payload 에 실어 alarm_flush_loop 의
    E2E latency 측정에 사용 (룰 기반 알람과 동일 경로). None 이면 측정 skip.
    """
    for channel, value in channel_values.items():
        if (channel, data_type) not in _INFERENCE_ENABLED_CHANNELS:
            continue
        # W0 quality_guard — 통신 단절/센서 오버플로우 값은 IF 윈도우 적재 skip
        # (학습 데이터 오염 + IF false negative 폭증 방지). raw 데이터 저장 흐름 영향 없음.
        status = classify_sensor_status(value, data_type)
        if status is not None:
            logger.info(
                "[anomaly_inference] skip device=%s ch=%s %s value=%s status=%s",
                device_id,
                channel,
                data_type,
                value,
                status,
            )
            continue
        win = _power_windows[(channel, data_type)]
        win.append(float(value))
        if len(win) < _INFERENCE_WINDOW:
            continue
        # W0 stuck — 윈도우 가득 + 모든 값 동일 (분산 0) → 센서 고정 고장 추정 → 추론 skip
        if is_inference_stuck(win):
            logger.info(
                "[anomaly_inference] skip device=%s ch=%s %s status=sensor_fault_stuck",
                device_id,
                channel,
                data_type,
            )
            continue

        try:
            sensor_identifier = f"power:device_{device_id}:ch{channel}:{data_type}"

            entry = await _get_or_load("power")
            if entry is None:
                AI_INFERENCE_FAILED_TOTAL.labels("power_if", "model_not_loaded").inc()
                continue
            # P2 전 — IF 추론 실행 시간 측정
            _infer_start = time.time()
            row = _build_feature_row(list(win), entry.window)
            score = float(entry.model.decision_function(row)[0])
            pred_int = int(entry.model.predict(row)[0])
            prediction = "anomaly" if pred_int == -1 else "normal"
            AI_INFERENCE_DURATION.labels("power_if").observe(time.time() - _infer_start)

            # D2 — Z-score 통계 이상 판정 (STEP D / plan §D2).
            z_score_anomaly, z_value = _zscore_check(win, float(value), threshold=3.0)
            if z_score_anomaly:
                logger.info(
                    "[zscore] device=%s ch=%s %s value=%s |z|=%.2f >= 3.0",
                    device_id,
                    channel,
                    data_type,
                    value,
                    z_value,
                )

            # E1 — Change Point (STEP E / plan §E1). 별도 _cp_windows (maxlen=60)
            # 채널별 누적 → two-window 비교. STABLE→SHIFT 전이 시점만 True.
            change_point, cp_meta = detect_change_point(
                (channel, data_type), float(value)
            )
            if change_point:
                logger.info(
                    "[change_point] device=%s ch=%s %s STABLE->SHIFT "
                    "mean_shift=%.2f std_ratio=%.2f",
                    device_id,
                    channel,
                    data_type,
                    cp_meta["mean_shift"],
                    cp_meta["std_ratio"],
                )

            # W3.2 ARIMA 분기 — sensor_identifier 단위 매칭. 학습 안 된 채널은
            # IF 단독 fallback (arima_violation=False). 모든 외부 호출 silent fail.
            arima_result: dict | None = None
            arima_violation = False
            try:
                entry_arima = await _get_or_load_arima("power", sensor_identifier)
                arima_result = _arima_forecast(list(win), entry_arima.model)
                arima_violation = bool(arima_result["is_violation"])
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
            except Exception as exc:
                logger.warning(
                    "[arima_forecast] failed sensor=%s: %s",
                    sensor_identifier,
                    exc,
                )

            threshold_risk = calculate_power_risk(value, data_type, device_id, channel)
            # §F — 5축 우선순위 엔진. base = 3축 매트릭스 (W3 회귀 보존) +
            # Z-score / CP 는 base=normal 일 때만 predict_warn 으로 격상.
            # escalation_source = "zscore" | "change_point" | "" — algorithm_source
            # 결정 시 "z/cp 가 실제 격상에 기여" 판정 근거 (코드리뷰 §2.1 보강).
            combined, escalation_source = combine_risk_5axis(
                threshold_risk,
                prediction,
                arima_violation,
                z_score_anomaly,
                change_point,
            )

            # W3.2 night_abnormal 시각 분기 — dummy 는 시각 무관 데이터 생성,
            # 추론 측이 measured_at hour KST 야간 + watt > 정격 30% 검사해 격상.
            # (향후 시각 컨텍스트 자동화 옵션 — SARIMAX / 다피처 IF / 동적 임계치. 필수 아님)
            entry_meta = get_channel_entry(device_id, channel)
            night_escalated = False
            if data_type == "watt" and _is_night_kst_iso(measured_at):
                rated_w = entry_meta.get("rated_w")
                if (
                    rated_w is not None
                    and value > float(rated_w) * _NIGHT_THRESHOLD_RATIO
                ):
                    escalated = _NIGHT_ESCALATION.get(combined, combined)
                    if escalated != combined:
                        logger.info(
                            "[night_abnormal] 야간 가동 의심 device=%s ch=%s "
                            "value=%s threshold=%.0f combined=%s->%s",
                            device_id,
                            channel,
                            value,
                            float(rated_w) * _NIGHT_THRESHOLD_RATIO,
                            combined,
                            escalated,
                        )
                        combined = escalated
                        night_escalated = True

            # W4.a + §F algorithm_source — AlarmRecord.algorithm_source 저장.
            # priority: night > combined > change_point* > arima > zscore* > IF.
            # *) z/cp 는 escalation_source 가 일치할 때만 라벨로 채택 — base 가 이미
            #    발화 등급인데 z/cp 발생한 케이스에서 라벨이 driver 와 어긋나는 문제
            #    방지 (코드리뷰 2026-05-19 §2.1 보강).
            if night_escalated:
                algorithm_source = "night_abnormal"
            elif prediction == "anomaly" and arima_violation:
                algorithm_source = "combined"
            elif escalation_source == "change_point":
                algorithm_source = "change_point"
            elif arima_violation:
                algorithm_source = "arima"
            elif escalation_source == "zscore":
                algorithm_source = "zscore"
            elif prediction == "anomaly":
                algorithm_source = "isolation_forest"
            else:
                algorithm_source = ""

            features = {
                "value": float(row[0, 0]),
                "roll_mean": float(row[0, 1]),
                "roll_std": float(row[0, 2]),
                "diff": float(row[0, 3]),
            }
            if arima_result is not None:
                features["arima_forecast"] = arima_result["forecast"]
                features["arima_ci_lower"] = arima_result["ci_lower"]
                features["arima_ci_upper"] = arima_result["ci_upper"]
                features["arima_violation"] = arima_violation

            logger.info(
                "[anomaly_inference] device=%s ch=%s %s value=%s "
                "threshold=%s pred=%s arima_v=%s z=%s cp=%s combined=%s "
                "score=%.4f arima_fc=%s ci=[%s,%s]",
                device_id,
                channel,
                data_type,
                value,
                threshold_risk,
                prediction,
                arima_violation,
                z_score_anomaly,
                change_point,
                combined,
                score,
                f"{arima_result['forecast']:.1f}" if arima_result else "n/a",
                f"{arima_result['ci_lower']:.1f}" if arima_result else "n/a",
                f"{arima_result['ci_upper']:.1f}" if arima_result else "n/a",
            )

            # should_fire = (발화 레벨) AND (rate limit 통과). False 면 helper 가
            # push/alarm forward skip, ML forward 만 진행 (운영 추적 유지).
            should_fire = combined in _FIRE_LEVELS
            if should_fire:
                now_ts = time.time()
                last_ts = _last_fired_at.get(sensor_identifier, 0.0)
                if now_ts - last_ts < RATE_LIMIT_SEC:
                    logger.info(
                        "[anomaly_inference] rate limited — sensor=%s combined=%s "
                        "(last %.1fs ago)",
                        sensor_identifier,
                        combined,
                        now_ts - last_ts,
                    )
                    should_fire = False
                else:
                    _last_fired_at[sensor_identifier] = now_ts

            label = entry_meta.get("name") or f"CH{channel}"
            # T1+T6: 운영자 친화 포맷. algorithm_source 는 anomaly_meta 로 분리되어
            # UI 칩으로 시각화 (zscore/급변/IF/ARIMA/IF+ARIMA/야간 가동). 따라서
            # summary 텍스트는 ML 기술용어 (score, combined) 와 출처 라벨 모두 제거.
            # 천단위 구분 (Python {:,.1f}) 으로 가독성 ↑.
            summary = f"{label} 이상 패턴 ({value:,.1f} W)"
            risk_level = _COMBINED_TO_RISK_LEVEL[combined]

            # ML forward + push + AlarmRecord forward 를 helper 단일 호출로 캡슐화.
            # helper 안에서 push 는 독립 task (C12 효과 보존), ML→alarm 은 sequential.
            # 모든 외부 호출 silent fail + Prometheus counter (anomaly_alarm.py).
            asyncio.create_task(
                forward_inference_e2e(
                    ml_payload={
                        "ml_model": None,
                        "model_version_snapshot": entry.version,
                        "sensor_type": "power",
                        "sensor_identifier": sensor_identifier,
                        "measured_at": measured_at,
                        "anomaly_score": score,
                        "prediction": prediction,
                        "risk_classified": combined,
                        "feature_snapshot_json": features,
                    },
                    alarm_payload={
                        "alarm_type": "power_anomaly_ai",
                        "risk_level": risk_level,
                        "source_device_id": str(device_id),
                        "measured_value": value,
                        "summary": summary,
                        "detected_at": measured_at,
                        "source_label": label,
                        # AlarmRecord.channel 에 저장 → get_short_message 가 channel_meta
                        # 로 라벨 ("송풍기A AI 이상 패턴 감지 (7925.8 W)") 생성.
                        "channel": channel,
                        # W4.a — AlarmRecord.algorithm_source 저장용 (plan §8).
                        "algorithm_source": algorithm_source,
                    },
                    push_payload={
                        "alarm_type": "power_anomaly_ai",
                        "risk_level": risk_level,
                        "source_label": label,
                        "summary": summary,
                        # T1+T6: message 단일 진실 공급원 필드 — drf-side tasks.py 의
                        # _push_to_ws 패턴과 동일. JS AlarmMapper 가 summary fallback
                        # 없이 message 만 읽도록 (drift 방지).
                        "message": summary,
                        "is_new_event": True,
                        "measured_value": value,
                        # 룰 기반 알람과 동일 키. alarm_flush_loop 이 E2E latency 측정.
                        "ingress_ts": ingress_ts,
                        "anomaly_meta": {
                            "combined_risk": combined,
                            "anomaly_score": score,
                            "device_id": device_id,
                            "channel": channel,
                            "data_type": data_type,
                            # W4.a — UI 알람 토스트/이벤트 패널이 algorithm 출처 칩
                            # 표시 (DB AlarmRecord.algorithm_source 와 동일 값).
                            "algorithm_source": algorithm_source,
                            # arima_result 가 있으면 forecast / CI 도 동행 — UI 가
                            # "예측 1091 ± 신뢰구간 [645, 1538]" 같은 디테일 표시 가능.
                            "arima_forecast": (
                                arima_result["forecast"] if arima_result else None
                            ),
                            "arima_ci": (
                                [arima_result["ci_lower"], arima_result["ci_upper"]]
                                if arima_result
                                else None
                            ),
                            # §F — 5축 정책 엔진 입력 4·5축 동행. UI 가 출처 칩
                            # 외에 어떤 축이 발화했는지 디테일 표시 가능 (예:
                            # "급변 감지 mean_shift=4.2 std_ratio=1.1").
                            "z_score_anomaly": z_score_anomaly,
                            "change_point": change_point,
                            "cp_mean_shift": (
                                cp_meta.get("mean_shift") if change_point else None
                            ),
                            "cp_std_ratio": (
                                cp_meta.get("std_ratio") if change_point else None
                            ),
                        },
                    },
                    should_fire=should_fire,
                )
            )
        except Exception as exc:
            AI_INFERENCE_FAILED_TOTAL.labels("power_if", "inference_error").inc()
            logger.warning(
                "[anomaly_inference] failed device=%s ch=%s %s: %s",
                device_id,
                channel,
                data_type,
                exc,
            )


def to_channel_list(
    channel_values: dict, anomaly_map: dict | None = None
) -> list[dict]:
    """
    채널별 측정값 딕셔너리를 DRF PowerData 저장 형식(리스트)으로 변환한다.
    값이 None인 채널은 통신 불능(comm_failure) 상태로 표시한다.

    anomaly_map : {channel:int → anomaly_type:str} — 더미 시뮬레이터에서만 채워짐.
                  해당 채널은 is_anomaly=True 로 저장된다.
    """
    anomaly_map = anomaly_map or {}
    return [
        {
            "channel": ch,
            "value": val,
            "sensor_status": "comm_failure" if val is None else "active",
            "risk_level": "normal",
            "is_anomaly": ch in anomaly_map,
            "anomaly_type": anomaly_map.get(ch),
        }
        for ch, val in channel_values.items()
    ]


def update_power_state(data_type: str, values: dict, measured_at: str) -> None:
    """
    power_latest 공유 상태를 갱신한다.
    갱신된 값은 다음 WebSocket 틱에서 build_equipment()를 통해 브라우저로 전달된다.
    """
    power_latest[data_type] = values
    power_latest["updated_at"] = measured_at


def _eval_axis_pct(value: float | None, rated, axis: str) -> str:
    """정격 % 환산 후 임계치 비교. 표시용 — DRF threshold_service와 동일 시맨틱(>=)."""
    if value is None or rated is None:
        return "normal"
    try:
        rated_f = float(rated)
    except (TypeError, ValueError):
        return "normal"
    if rated_f == 0:
        return "normal"
    pct = value / rated_f * 100
    cfg = _PCT_THRESHOLDS[axis]
    if cfg["bidirectional"]:
        if pct <= cfg["danger_low"] or pct >= cfg["danger_high"]:
            return "danger"
        if pct <= cfg["warning_low"] or pct >= cfg["warning_high"]:
            return "warning"
        return "normal"
    if pct >= cfg["danger"]:
        return "danger"
    if pct >= cfg["warning"]:
        return "warning"
    return "normal"


def _max_risk(levels: list[str]) -> str:
    order = {"normal": 0, "warning": 1, "danger": 2}
    return max(levels, key=lambda lv: order.get(lv, 0))


def _legacy_watt_risk(watt: float | None) -> str:
    """channel_meta 미수신 시 watt 절대값 fallback (POWER_THRESHOLDS)."""
    if watt is None:
        return "normal"
    if watt > POWER_THRESHOLDS["danger"]:
        return "danger"
    if watt > POWER_THRESHOLDS["caution"]:
        return "warning"
    return "normal"


def build_equipment() -> tuple[list[dict], float]:
    """
    power_latest 공유 상태를 읽어 equipment 목록과 총 전력(kW)을 조립한다.

    [축별 risk 표시]
    채널 정격(channel_meta[ch][rated_*])을 사용해 W·A·V 각 축의 % 위험도를 산출.
    정격 미입력 시 power_risk만 POWER_THRESHOLDS 절대값으로 fallback.
    종합 risk_level = max(power_risk, current_risk, voltage_risk).

    [단일 진실 공급원]
    본 함수의 risk 산출은 대시보드 색상 표시용. 실제 알람 트리거는 DRF의
    apps.monitoring.services.power_alarm.trigger_power_alarms()가 담당.
    """
    if not any(
        [power_latest["watt"], power_latest["current"], power_latest["voltage"]]
    ):
        return [], 0.0

    equipment = []
    total_w = 0.0

    for ch in range(1, 17):
        watt = power_latest["watt"].get(ch)
        voltage = power_latest["voltage"].get(ch)
        current = power_latest["current"].get(ch)
        onoff = power_latest["onoff"].get(str(ch))

        is_comm = watt is None and voltage is None and current is None
        sensor_status = "comm_failure" if is_comm else "active"

        entry = get_channel_entry(None, ch)
        label = entry.get("name") or f"CH{ch}"

        if is_comm:
            power_risk = current_risk = voltage_risk = risk_level = "normal"
        else:
            rated_w = entry.get("rated_w")
            if rated_w is not None:
                power_risk = _eval_axis_pct(watt, rated_w, "watt")
            else:
                power_risk = _legacy_watt_risk(watt)
            current_risk = _eval_axis_pct(current, entry.get("rated_a"), "current")
            voltage_risk = _eval_axis_pct(voltage, entry.get("rated_v"), "voltage")
            risk_level = _max_risk([power_risk, current_risk, voltage_risk])
            if watt is not None:
                total_w += watt

        equipment.append(
            {
                "name": label,
                "watt": watt,
                "voltage": voltage,
                "current": current,
                "onoff": onoff,
                "sensor_status": sensor_status,
                "risk_level": risk_level,
                "power_risk": power_risk,
                "current_risk": current_risk,
                "voltage_risk": voltage_risk,
            }
        )

    return equipment, round(total_w / 1000, 3)
