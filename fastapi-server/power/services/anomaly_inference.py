# power/services/anomaly_inference.py — 전력 채널별 AI 추론 + 알람 결정
#
# 데이터 흐름:
#   IN  : power_router 가 채널별 측정값 dict + measured_at 전달
#         channel_values = {ch:int → value:float|None}
#   OUT : 1) WebSocket — push_alarm (Redis diconai:ws:alarms 큐)
#         2) DRF       — forward_inference_e2e (MLAnomalyResult + AlarmRecord)
#         3) DRF AI mute — mark_ai_recent (ai_fired:* 키, AI 발화 호환)
#         4) Prometheus — POWER_AI_* counter 다수 + AI_BROADCAST_LATENCY
#
# 결정 매트릭스:
#   AI 5 state (DISABLED/WARMING_UP/FIRED/INFERRED_NORMAL/INFERRED_FAILED)
#     × static_risk (normal/warning/danger) → decide_alarm.decide_alarm 이 source 결정
#     → source=ai (AI 발화) 또는 source=static_* (정적 cover).
import asyncio
import logging
import time

from fastapi import HTTPException

from ai.risk_combine import combine_risk_5axis
from ai.router import (
    _arima_forecast,
    _build_feature_row,
    _get_or_load,
    _get_or_load_arima,
)
from core.constants import AI_TO_RULE_LEVEL
from core.metrics import (
    AI_BROADCAST_LATENCY,
    AI_INFERENCE_DURATION,
    AI_INFERENCE_FAILED_TOTAL,
    POWER_AI_ALARM_FIRED_TOTAL,
    POWER_AI_AXIS_FIRED_TOTAL,
    POWER_AI_COMBINED_TOTAL,
    POWER_AI_INFERENCE_TOTAL,
    POWER_AI_QUALITY_SKIP_TOTAL,
    POWER_AI_RATE_LIMITED_TOTAL,
)
from power.services.change_point_service import detect_change_point
from power.services.channel_meta_cache import get_channel_entry
from power.services.decide_alarm import AlarmDecision, decide_alarm
from power.services.night_escalation import (
    _is_night_kst_iso,
    _NIGHT_ESCALATION,
    _NIGHT_THRESHOLD_RATIO,
)
from power.services.quality_guard import classify_sensor_status, is_inference_stuck
from power.services.threshold_eval import (
    calculate_power_risk,
    evaluate_static_risk_from_cache,
    get_static_threshold_abs,
)
from power.services.zscore_anomaly import (
    _INFERENCE_WINDOW,
    _power_windows,
    _zscore_check,
)
from services.ai_mute import AIInferenceState, mark_ai_recent, mark_ai_state
from services.anomaly_alarm import forward_inference_e2e
from websocket.services.alarm_queue import push_alarm

logger = logging.getLogger(__name__)

# combined_risk → RiskLevel 매핑 (현재 미사용 — AlarmPayload.risk_level 직매핑 도입 시 활용).
_COMBINED_TO_RISK_LEVEL = {
    "normal": "normal",
    "caution": "warning",
    "predict_warn": "warning",
    "warning": "warning",
    "danger": "danger",
}

# 알람 발화 등급 (combined_risk) — normal 외 모두 fire 후보.
_FIRE_LEVELS = {"caution", "predict_warn", "warning", "danger"}

# AI 추론 활성 채널 (watt 만). 부하 프로파일 다양성 검증용 채널 선정 —
# ch1=압연기 / ch9=메인 전력반 / ch14=공조 / ch15=조명.
# 채널별 IF + ARIMA 모델을 sensor_identifier (mac 단위) 로 매칭해 별도 학습·로드.
_INFERENCE_ENABLED_CHANNELS: set[tuple[int, str]] = {
    (1, "watt"),
    (9, "watt"),
    (14, "watt"),
    (15, "watt"),
}

# 같은 sensor_identifier 알람 push 폭주 회피 — 60초당 1회 (operator UX).
# ML forward 는 매번 호출 (운영 추적). rate limit 은 push 단계만 차단.
_last_fired_at: dict[str, float] = {}
RATE_LIMIT_SEC = 60

# algorithm_source 코드 → 운영자 친화 워딩 (drf-server constants.ALGORITHM_SOURCE_PHRASE 와 단일 동기).
# dict 미정의 코드는 "AI 이상 탐지" fallback.
_ALGORITHM_SOURCE_PHRASE = {
    "isolation_forest": "이상 수치 탐지",
    "arima": "이상 패턴 탐지",
    "combined": "이상 수치·패턴 동시 탐지",
    "zscore": "통계 이상 수치",
    "change_point": "패턴 변화 탐지",
    "night_abnormal": "야간 이상 가동",
}


def _build_static_push_payload(
    decision: AlarmDecision,
    label: str,
    value: float,
    ingress_ts: float | None,
    threshold_value: float | None = None,
) -> dict:
    """source=static_* 알람 push payload 를 조립한다.

    anomaly_meta 없음 (AI 추론 결과 부재 또는 미반영). summary 는 [긴급]/[주의]
    prefix + 라벨 + 측정값 + decision.reason 조합. AI source 는 별 inline 빌더 사용.

    threshold_value 가 있으면 payload 에 동봉해 모달의 "기준 X 초과" 표시 컨텍스트 제공.
    """
    prefix = "[긴급]" if decision.risk_level == "danger" else "[주의]"
    tail = (
        f" — {decision.reason}"
        if decision.reason
        else " — 즉시 확인하고 관리자에게 보고하세요."
    )
    summary = f"{prefix} {label} 전력 과부하 ({value:,.1f}W){tail}"
    message = f"{label} 임계치 초과 ({value:,.1f} W)"
    payload = {
        "alarm_type": decision.alarm_type,
        "risk_level": decision.risk_level,
        "source": decision.source,
        "reason": decision.reason,
        "source_label": label,
        "summary": summary,
        "message": message,
        "is_new_event": True,
        "measured_value": value,
        "ingress_ts": ingress_ts,
    }
    if threshold_value is not None:
        payload["threshold_value"] = threshold_value
    return payload


async def _push_static_decision(
    decision: AlarmDecision,
    label: str,
    value: float,
    ingress_ts: float | None,
    threshold_value: float | None = None,
) -> None:
    """decide_alarm 결정 (source=static_*) 의 push 를 실행한다.

    DISABLED / WARMING_UP / INFERRED_FAILED 분기 공통. push 실패는 silent
    (logger.exception 만, 다른 채널 평가는 계속).
    """
    payload = _build_static_push_payload(
        decision, label, value, ingress_ts, threshold_value
    )
    try:
        await push_alarm(payload)
    except Exception:
        logger.exception(
            "[anomaly_inference] static push failed source=%s", decision.source
        )


async def process_anomaly_inference(
    device_id: str | None,
    channel_values: dict,
    data_type: str,
    measured_at: str,
    ingress_ts: float | None = None,
) -> None:
    """전력 채널별 AI 추론 + 정적 임계 평가 후 단일 알람 결정·push 를 수행한다.

    채널마다 다음 5단계:
      1. quality_guard — 통신 단절·overflow·stuck 시 AI 평가 skip
      2. AI 비활성 채널 → DISABLED 마킹 + 정적 평가 + decide_alarm
      3. AI 활성 채널 + 윈도우 빌드 중 → WARMING_UP + 정적 평가
      4. AI 활성 채널 + 윈도우 빌드 완료 → IF/ARIMA/Z/CP/threshold 5축 추론
         · combined ∈ FIRE_LEVELS → FIRED + rate limit (60s) 통과 시 push
         · combined == normal → INFERRED_NORMAL + ML forward 만
         · 추론 예외 → INFERRED_FAILED + 정적 폴백
      5. decide_alarm 매트릭스 → source 결정 → push (단일)

    [push 정책]
      · source=ai      : AI_BROADCAST_LATENCY observe + push_alarm + ML/Alarm forward
      · source=static_*: push_alarm 만 (AlarmRecord 영속화 미포함)

    Args:
        device_id: PowerDevice mac 또는 None.
        channel_values: {채널 int → 측정값 float|None}.
        data_type: "watt" / "current" / "voltage" / "onoff".
        measured_at: ISO 8601 측정 시각 (KST 야간 격상 게이트 입력).
        ingress_ts: 핸들러 진입 시각 (alarm_flush_loop E2E latency 측정용).
    """
    for channel, value in channel_values.items():
        # 1. 센서 통신 단절/오버플로우 → AI 평가 skip (state 마킹 없음).
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
            POWER_AI_QUALITY_SKIP_TOTAL.labels(status).inc()
            continue

        # 정적 평가 (모든 채널 공통) — DRF threshold-meta sync 캐시 read.
        static_risk = evaluate_static_risk_from_cache(
            value, data_type, device_id, channel
        )
        # 모달 "기준 X 초과" 컨텍스트용 절대값 (normal 시 None).
        static_threshold_abs = get_static_threshold_abs(
            static_risk, data_type, device_id, channel
        )
        entry_meta = get_channel_entry(device_id, channel)
        label = entry_meta.get("name") or f"CH{channel}"

        # 2. AI 비활성 채널 → DISABLED 분기.
        if (channel, data_type) not in _INFERENCE_ENABLED_CHANNELS:
            await mark_ai_state(
                device_id, channel, data_type, AIInferenceState.DISABLED
            )
            decision = decide_alarm(
                AIInferenceState.DISABLED,
                ai_combined_risk="normal",
                static_risk=static_risk,
            )
            if decision is not None:
                await _push_static_decision(
                    decision, label, float(value), ingress_ts, static_threshold_abs
                )
            continue

        # 3. 윈도우 누적 — 부족 시 WARMING_UP.
        win = _power_windows[(channel, data_type)]
        win.append(float(value))
        if len(win) < _INFERENCE_WINDOW:
            await mark_ai_state(
                device_id, channel, data_type, AIInferenceState.WARMING_UP
            )
            decision = decide_alarm(
                AIInferenceState.WARMING_UP,
                ai_combined_risk="normal",
                static_risk=static_risk,
            )
            if decision is not None:
                await _push_static_decision(
                    decision, label, float(value), ingress_ts, static_threshold_abs
                )
            continue

        # 윈도우가 차도 모든 값이 동일하면 센서 고정 고장 — AI 평가 skip,
        # state 마킹 없이 직전 state 유지 (quality_guard 동등 취급).
        if is_inference_stuck(win):
            logger.info(
                "[anomaly_inference] skip device=%s ch=%s %s status=sensor_fault_stuck",
                device_id,
                channel,
                data_type,
            )
            POWER_AI_QUALITY_SKIP_TOTAL.labels("sensor_fault_stuck").inc()
            continue

        # 4. AI 활성 채널 + 윈도우 빌드 완료 → IF/ARIMA/Z/CP/threshold 추론.
        try:
            # sensor_identifier 는 DRF ActiveMLModelView 의 매칭 키.
            # 학습 명령(train_anomaly_model)이 같은 포맷으로 등록한다.
            sensor_identifier = f"power:device_{device_id}:ch{channel}:{data_type}"

            entry = await _get_or_load("power", sensor_identifier=sensor_identifier)
            if entry is None:
                AI_INFERENCE_FAILED_TOTAL.labels("power_if", "model_not_loaded").inc()
                continue
            POWER_AI_INFERENCE_TOTAL.inc()
            _infer_start = time.time()
            row = _build_feature_row(list(win), entry.window)
            score = float(entry.model.decision_function(row)[0])
            pred_int = int(entry.model.predict(row)[0])
            prediction = "anomaly" if pred_int == -1 else "normal"
            AI_INFERENCE_DURATION.labels("power_if").observe(time.time() - _infer_start)

            # Z-score (STEP D) — 슬라이딩 윈도우 통계 이상.
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

            # Change Point (STEP E) — 별도 _cp_windows (maxlen=60), two-window 비교.
            # STABLE→SHIFT 전이 시점만 True.
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

            # ARIMA 분기 — sensor_identifier 단위 매칭. 학습 안 된 채널은
            # IF 단독 fallback (arima_violation=False). 외부 호출 silent fail.
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
            # 5축 우선순위 엔진. base = 3축 (threshold/IF/ARIMA), Z/CP 는 base=normal 일
            # 때만 predict_warn 으로 격상. escalation_source 는 격상에 기여한 축.
            combined, escalation_source = combine_risk_5axis(
                threshold_risk,
                prediction,
                arima_violation,
                z_score_anomaly,
                change_point,
            )

            # 야간 가동 격상 — KST 야간 + watt > 정격 30% 일 때 한 단계 격상.
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

            POWER_AI_COMBINED_TOTAL.labels(combined).inc()

            # algorithm_source priority — night > combined > change_point > arima > zscore > IF.
            # z/cp 는 escalation_source 가 일치할 때만 라벨 채택 (base 발화 중 z/cp 발생 시
            # 라벨이 실제 driver 와 어긋나는 문제 방지).
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

            # ML forward payload — decide_alarm 결과 무관하게 항상 전송 (운영 추적).
            ml_payload = {
                "ml_model": None,
                "model_version_snapshot": entry.version,
                "sensor_type": "power",
                "sensor_identifier": sensor_identifier,
                "measured_at": measured_at,
                "anomaly_score": score,
                "prediction": prediction,
                "risk_classified": combined,
                "feature_snapshot_json": features,
            }

            # 5축 발화 분포 카운터 — combined 가 발화 등급일 때 각 축의 기여 기록.
            # rate limit 무관 (추론 분포 자체 추적). 특정 축이 과도하면 임계치 조정 신호.
            if combined in _FIRE_LEVELS:
                if prediction == "anomaly":
                    POWER_AI_AXIS_FIRED_TOTAL.labels("if").inc()
                if arima_violation:
                    POWER_AI_AXIS_FIRED_TOTAL.labels("arima").inc()
                if z_score_anomaly:
                    POWER_AI_AXIS_FIRED_TOTAL.labels("zscore").inc()
                if change_point:
                    POWER_AI_AXIS_FIRED_TOTAL.labels("change_point").inc()
                if night_escalated:
                    POWER_AI_AXIS_FIRED_TOTAL.labels("night").inc()

            # AI 결과 → state 마킹 + rate limit. 미통과 시 push/matrix skip, ML forward 만.
            if combined in _FIRE_LEVELS:
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
                    POWER_AI_RATE_LIMITED_TOTAL.inc()
                    asyncio.create_task(forward_inference_e2e(ml_payload, None))
                    continue
                _last_fired_at[sensor_identifier] = now_ts
                POWER_AI_ALARM_FIRED_TOTAL.labels(algorithm_source).inc()
                await mark_ai_state(
                    device_id, channel, data_type, AIInferenceState.FIRED
                )
                # DRF AI mute (ai_fired:* 키) 호환 — rule 알람과 발화 중복 방지.
                rule_level = AI_TO_RULE_LEVEL.get(combined, combined)
                asyncio.create_task(mark_ai_recent(device_id, channel, rule_level))
                ai_state = AIInferenceState.FIRED
                ai_combined = combined
            else:
                await mark_ai_state(
                    device_id, channel, data_type, AIInferenceState.INFERRED_NORMAL
                )
                ai_state = AIInferenceState.INFERRED_NORMAL
                ai_combined = "normal"

            # decide_alarm 매트릭스 — AI state × static_risk → 단일 source 결정.
            decision = decide_alarm(ai_state, ai_combined, static_risk)
            if decision is None:
                asyncio.create_task(forward_inference_e2e(ml_payload, None))
                continue

            if decision.source == "ai":
                phrase = _ALGORITHM_SOURCE_PHRASE.get(algorithm_source, "AI 이상 탐지")
                summary = f"{label} {phrase} ({value:,.1f} W)"
                push_payload = {
                    "alarm_type": "power_anomaly_ai",
                    "risk_level": decision.risk_level,
                    "source": decision.source,
                    "reason": decision.reason,
                    "source_label": label,
                    "summary": summary,
                    "message": summary,
                    "is_new_event": True,
                    "measured_value": value,
                    "ingress_ts": ingress_ts,
                    "anomaly_meta": {
                        "combined_risk": combined,
                        "anomaly_score": score,
                        "device_id": device_id,
                        "channel": channel,
                        "data_type": data_type,
                        "algorithm_source": algorithm_source,
                        "arima_forecast": (
                            arima_result["forecast"] if arima_result else None
                        ),
                        "arima_ci": (
                            [arima_result["ci_lower"], arima_result["ci_upper"]]
                            if arima_result
                            else None
                        ),
                        "z_score_anomaly": z_score_anomaly,
                        "change_point": change_point,
                        "cp_mean_shift": (
                            cp_meta.get("mean_shift") if change_point else None
                        ),
                        "cp_std_ratio": (
                            cp_meta.get("std_ratio") if change_point else None
                        ),
                    },
                }
                alarm_payload = {
                    "alarm_type": "power_anomaly_ai",
                    "risk_level": decision.risk_level,
                    "source_device_id": str(device_id),
                    "measured_value": value,
                    "summary": summary,
                    "detected_at": measured_at,
                    "source_label": label,
                    "channel": channel,
                    "algorithm_source": algorithm_source,
                    "source": decision.source,
                }
                if ingress_ts is not None:
                    AI_BROADCAST_LATENCY.observe(time.time() - ingress_ts)
            else:
                # static_cover_miss — AI 활성 채널 + AI 정상 + 정적 발화.
                # AlarmRecord 영속화는 본 흐름 비포함 (alarm_payload=None).
                push_payload = _build_static_push_payload(
                    decision, label, float(value), ingress_ts, static_threshold_abs
                )
                alarm_payload = None

            try:
                await push_alarm(push_payload)
            except Exception:
                logger.exception(
                    "[anomaly_inference] push failed source=%s", decision.source
                )

            asyncio.create_task(forward_inference_e2e(ml_payload, alarm_payload))
        except Exception as exc:
            AI_INFERENCE_FAILED_TOTAL.labels("power_if", "inference_error").inc()
            logger.warning(
                "[anomaly_inference] failed device=%s ch=%s %s: %s",
                device_id,
                channel,
                data_type,
                exc,
            )
            # 추론 실패 → INFERRED_FAILED 마킹 + 정적 폴백. 폴백 자체 실패 시 silent.
            try:
                await mark_ai_state(
                    device_id, channel, data_type, AIInferenceState.INFERRED_FAILED
                )
                decision = decide_alarm(
                    AIInferenceState.INFERRED_FAILED,
                    ai_combined_risk="normal",
                    static_risk=static_risk,
                )
                if decision is not None:
                    await _push_static_decision(
                        decision, label, float(value), ingress_ts, static_threshold_abs
                    )
            except Exception:
                logger.exception(
                    "[anomaly_inference] inference-failed fallback failed device=%s ch=%s",
                    device_id,
                    channel,
                )
