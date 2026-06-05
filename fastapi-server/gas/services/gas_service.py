# gas/services/gas_service.py — 가스 측정값 수신 처리 서비스
#
# 데이터 흐름:
#   IN  : gas_router 가 넘기는 GasDataPayload (검증된 9종 가스 측정값)
#   OUT : 1) DRF POST /api/monitoring/gas/ — 측정값 영속화 (DRF 내부에서
#            임계치 초과 시 Celery 알람 태스크 트리거)
#         2) latest_gas_snapshot 갱신 — 다음 WebSocket 틱에 브라우저로 전달
#         3) (AI) IF 이상탐지 적중 시 push_alarm 으로 실시간 알람 직접 push +
#            forward_inference_e2e 로 ML 결과/AlarmRecord 비동기 저장
#
# AI 추론: co+h2s+co2 30틱 슬라이딩 윈도우 → change point 게이트 → IF 추론.
#          ARIMA 잔차 피처는 모델 존재 시에만 가산.
import time
import logging
import asyncio
import joblib
import numpy as np
import ruptures as rpt
from pathlib import Path
from core.config import settings
from services.ai_mute import (
    AIInferenceState,
    mark_gas_ai_recent,
    mark_gas_ai_state,
)
from services.anomaly_alarm import forward_inference_e2e
from websocket.services.alarm_queue import (
    push_alarm,
)  # 이성현 추가 — 브라우저 실시간 알람 push
from datetime import datetime, timezone


from core.gas_thresholds import calculate_individual_risks
from gas.schemas.gas import GasDataPayload
from services.drf_client import post_to_drf
from core.metrics import (
    AI_INFERENCE_DURATION,
    AI_INFERENCE_FAILED_TOTAL,
    SENSOR_LAST_RECEIVED,
    GAS_AI_INFERENCE_TOTAL,
    GAS_CP_DETECTED_TOTAL,
    GAS_AI_RATE_LIMITED_TOTAL,
    GAS_AI_ALARM_FIRED_TOTAL,
)
from websocket.snap_store import store_gas_snapshot  # 이성현 수정 — Redis 이관
from collections import (
    deque,
)
from ai.router import (
    _get_or_load,
    _build_multi_feature_row,
)
from gas.constants import GAS_FIELDS  # 이성현 추가 — 9종 가스 순서 단일 공급원


logger = logging.getLogger(__name__)

# 이성현 추가 — ARIMA pkl 모듈 레벨 로드 (실시간 잔차 계산용).
#   statsmodels pickle 임포트 버그 대비 try-except — 실패 시 12피처로 폴백.
_arima_models: dict = {}
for _gn in GAS_FIELDS:  # 이성현 수정 — 3종 → 9종 ARIMA 로드
    _p = Path(settings.ML_MODELS_DIR) / f"arima_{_gn}.pkl"
    if _p.exists():
        try:
            _arima_models[_gn] = joblib.load(_p)["result"]
        except Exception:
            pass


# 이성현 추가 — 슬라이딩 윈도우에서 체인지 포인트 탐지
# penalty 미지정 시 settings.DEMO_GAS_CP_PENALTY 사용 (env override). 시연 시 1.0
# 으로 낮춰 부드러운 RAMP_UP 도 잡고, 운영 시 3.0 (default) 로 false positive 억제.
def _detect_change_point(values: list[float], penalty: float | None = None) -> bool:
    """30틱 윈도우에서 패턴 전환 시점이 있으면 True 반환."""
    pen = settings.DEMO_GAS_CP_PENALTY if penalty is None else penalty
    arr = np.array(values, dtype=np.float64).reshape(-1, 1)
    try:
        model = rpt.Pelt(model="rbf").fit(arr)
        result = model.predict(pen=pen)
        actual_cps = [cp for cp in result if cp < len(arr)]
        return len(actual_cps) > 0
    except Exception:
        return False


# 이성현 수정 — 3종 개별 변수 → 9종 dict (GAS_FIELDS 순서 보존)
_gas_windows: dict[str, deque] = {g: deque(maxlen=30) for g in GAS_FIELDS}

# 이성현 추가 — 같은 센서 60초당 1회만 알람 발화 (전력 서비스와 동일 rate limit 패턴).
# 하드코딩 제거 — settings.GAS_AI_RATE_LIMIT_SEC 로 환경별 조정 가능.
# DRF 의 ALARM_REPOPUP_COOLDOWN_SEC 과 값을 맞추려면 .env 에서 함께 변경할 것.
_gas_last_fired_at: dict[str, float] = {}
GAS_RATE_LIMIT_SEC = settings.GAS_AI_RATE_LIMIT_SEC

DRF_GAS_PATH = "/api/monitoring/gas/"


async def process_gas_data(payload: GasDataPayload) -> dict:
    """가스 데이터 수신 후 전체 처리 흐름을 조율한다.

    1. 가스별 위험도(individual_risks)를 계산한다.
    2. (AI) co+h2s+co2 윈도우가 차면 change point 게이트 후 IF 이상탐지 —
       적중 시 실시간 push_alarm + ML 결과 비동기 저장 (60s rate limit).
    3. DRF에 측정값과 위험도를 저장한다 (DRF → Celery 태스크 → 알람 push).
    4. latest_gas_snapshot을 갱신해 WebSocket 브로드캐스트에 포함시킨다.

    DRF 통신 실패는 센서 장비에 적절한 HTTP 응답을 돌려주기 위해 예외로 전파한다.
    """
    # 센서 마지막 수신 시각 갱신 — 5분 이상 없으면 통신 이상으로 판단.
    SENSOR_LAST_RECEIVED.labels("gas", payload.device_id).set(time.time())

    gas_values = {
        "o2": payload.o2,
        "co": payload.co,
        "co2": payload.co2,
        "h2s": payload.h2s,
        "lel": payload.lel,
        "no2": payload.no2,
        "so2": payload.so2,
        "o3": payload.o3,
        "nh3": payload.nh3,
        "voc": payload.voc,
    }
    individual_risks = calculate_individual_risks(gas_values)

    # 이성현 수정 — 9종 윈도우 동시 append (gas_values는 위에서 이미 9종 보유)
    for _g in GAS_FIELDS:
        _gas_windows[_g].append(gas_values[_g])
    if len(_gas_windows["co"]) >= 30:
        # 9종 중 하나라도 패턴 변화 시 추론 진행
        cp_detected = any(
            _detect_change_point(list(_gas_windows[_g])) for _g in GAS_FIELDS
        )
        if not cp_detected:
            logger.debug("[체인지 포인트] 패턴 변화 없음 — 추론 스킵")
        else:
            GAS_CP_DETECTED_TOTAL.inc()
            logger.debug("[체인지 포인트] 패턴 변화 감지 — IF 추론 진행")
            try:
                # 이성현 수정 — 학습 sensor_identifier와 동일 (gas:sensor_1:co_h2s_co2_o2_..._voc)
                _model_identifier = "gas:sensor_1:" + "_".join(GAS_FIELDS)
                entry = await _get_or_load("gas", sensor_identifier=_model_identifier)
                if entry is None:
                    # 모델 미등록 — AI 없이 룰 기반으로만 처리. DRF 저장은 아래 로직으로 계속 진행.
                    AI_INFERENCE_FAILED_TOTAL.labels("gas_if", "model_not_loaded").inc()
                    raise RuntimeError("gas IF 모델 미등록")
                # IF 추론 실행 시간 측정
                _infer_start = time.time()
                # 이성현 수정 — 9종 windows를 GAS_FIELDS 순서대로 전달 (학습 피처 순서와 일치)
                row = _build_multi_feature_row(
                    {_g: list(_gas_windows[_g]) for _g in GAS_FIELDS},
                    entry.window,
                    arima_results=_arima_models if _arima_models else None,
                )
                pred = int(entry.model.predict(row)[0])
                score = float(entry.model.decision_function(row)[0])
                AI_INFERENCE_DURATION.labels("gas_if").observe(
                    time.time() - _infer_start
                )
                GAS_AI_INFERENCE_TOTAL.inc()

                if (
                    pred == -1
                ):  # AI가 이상 패턴으로 판단했을 때만 실행 (-1=이상, 1=정상)
                    # 이성현 수정 — should_fire=True 하드코딩 제거, 60초 rate limit 적용
                    # 이성현 수정 — 9종 식별자 (장치ID + 9종 가스)
                    sensor_identifier = f"gas:{payload.device_id}:" + "_".join(
                        GAS_FIELDS
                    )
                    # 이성현 추가 — 위험/주의 등급 가스만 추려 알람 메시지·대표 가스로 사용
                    _risky = [
                        g
                        for g in GAS_FIELDS
                        if individual_risks.get(f"{g}_risk") in ("warning", "danger")
                    ]
                    _gas_detail = (
                        " ".join(f"{g.upper()}:{gas_values[g]}" for g in _risky)
                        if _risky
                        else "패턴 이상 (개별 임계 정상)"
                    )
                    _lead_gas = (
                        _risky[0] if _risky else "co"
                    )  # 대표 가스 (메트릭/payload용)
                    now_ts = time.time()  # 지금 이 순간의 시각 (초 단위 숫자)
                    last_ts = _gas_last_fired_at.get(
                        sensor_identifier, 0.0
                    )  # 이 센서가 마지막으로 알람을 쐈던 시각 (처음이면 0.0)
                    should_fire = (
                        (now_ts - last_ts) >= GAS_RATE_LIMIT_SEC
                    )  # 마지막 알람 후 60초 이상 지났으면 True, 아니면 False
                    if not should_fire:
                        GAS_AI_RATE_LIMITED_TOTAL.inc()
                    if should_fire:  # 60초가 지났을 때만 실행
                        _gas_last_fired_at[sensor_identifier] = (
                            now_ts  # 방금 쏜 시각 기록 (다음 번 비교에 사용)
                        )
                        logger.warning(  # 서버 로그에 이상 감지 출력 (60초 지났을 때만)
                            f"[AI 이상탐지] 9종 이상 감지 | device={payload.device_id} | {_gas_detail}"
                        )
                        # DRF gas_alarm 가드용 mute 마킹 — 추론 가스 9종 룰 60s 억제.
                        # sensor_id 자리에 payload.device_id (mac) — DRF gas_alarm 측은
                        # sensor.device_name (mac) 으로 동일 키 read.
                        for _g in GAS_FIELDS:  # 이성현 수정 — 9종 전부 mute
                            await mark_gas_ai_recent(
                                sensor_id=payload.device_id,
                                gas_type=_g,
                                rule_level="danger",
                            )
                            await mark_gas_ai_state(
                                sensor_id=payload.device_id,
                                gas_type=_g,
                                state=AIInferenceState.FIRED,
                            )
                    # 이성현 — forward_inference_e2e: ML 결과는 매번 저장,
                    #   alarm_payload 는 should_fire=True 일 때만 전달.
                    # create_task 미처리 예외가 "Task exception was never retrieved"
                    # 경고로 조용히 사라지지 않도록 done callback 으로 error 로그 기록.
                    _t = asyncio.create_task(
                        forward_inference_e2e(
                            ml_payload={
                                "ml_model": None,
                                "model_version_snapshot": entry.version,
                                "sensor_type": "gas",
                                "sensor_identifier": sensor_identifier,
                                "measured_at": payload.timestamp.isoformat(),
                                "anomaly_score": score,
                                "prediction": "anomaly",
                                "risk_classified": "danger",
                                # 이성현 수정 — 9종 전부 기록
                                "feature_snapshot_json": {
                                    _g: gas_values[_g] for _g in GAS_FIELDS
                                },
                            },
                            alarm_payload={  # should_fire=True일 때만 AlarmRecord 저장
                                "alarm_type": "gas_anomaly_ai",
                                "risk_level": "danger",
                                "source_sensor_id": payload.device_id,
                                # 이성현 수정 — 대표 위험 가스 + 위험 가스 요약 메시지
                                "gas_type": _lead_gas,
                                "measured_value": gas_values[_lead_gas],
                                "summary": f"가스 이상 감지 (AI) | {_gas_detail}",
                                "detected_at": payload.timestamp.isoformat(),
                                "source_label": "가스센서 AI 이상탐지",
                            }
                            if should_fire
                            else None,
                        )
                    )
                    _t.add_done_callback(
                        lambda t: logger.error(
                            "[forward_inference_e2e] bg task failed: %s", t.exception()
                        )
                        if not t.cancelled() and t.exception() is not None
                        else None
                    )
                    # 이성현 추가 — 브라우저 실시간 알람 push (should_fire=True일 때만)
                    if should_fire:
                        # 이성현 수정 — 대표 위험 가스 라벨로 메트릭 기록
                        GAS_AI_ALARM_FIRED_TOTAL.labels(_lead_gas, "danger").inc()
                        _p = asyncio.create_task(
                            push_alarm(
                                {
                                    "alarm_type": "gas_anomaly_ai",
                                    "risk_level": "danger",
                                    "source_label": "가스센서 AI 이상탐지",
                                    # 이성현 수정 — 위험 가스 요약 메시지 (9종 중 warning/danger만)
                                    "summary": f"가스 이상 감지 (AI) | {_gas_detail}",
                                    "message": f"가스 이상 감지 (AI) | {_gas_detail}",
                                    "is_new_event": True,
                                    "gas_type": _lead_gas,
                                    "measured_value": gas_values[_lead_gas],
                                }
                            )
                        )
                        _p.add_done_callback(
                            lambda t: logger.error(
                                "[push_alarm] bg task failed: %s", t.exception()
                            )
                            if not t.cancelled() and t.exception() is not None
                            else None
                        )
            except Exception as e:
                AI_INFERENCE_FAILED_TOTAL.labels("gas_if", "inference_error").inc()
                logger.error(f"[AI 추론 실패] {e}")

    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": payload.timestamp.isoformat(),
        "ingress_ts": time.time(),
        "co": payload.co,
        "h2s": payload.h2s,
        "co2": payload.co2,
        "o2": payload.o2,
        "no2": payload.no2,
        "so2": payload.so2,
        "o3": payload.o3,
        "nh3": payload.nh3,
        "voc": payload.voc,
        **individual_risks,
        "raw_payload": payload.model_dump(mode="json"),
        # IF 학습 라벨 — 시뮬레이터에서만 채워짐. 운영 페이로드는 None.
        # serializer 가 anomaly_type 값이 있으면 is_anomaly=True 와 함께 저장 (G2).
        "is_anomaly": payload.anomaly_type is not None,
        "anomaly_type": payload.anomaly_type,
    }

    # DRF 저장을 fire-and-forget으로 분리 — E2E latency 개선
    # 기존: await post_to_drf()가 DRF 응답을 기다리는 동안(~200ms) 이벤트 루프 블로킹.
    #       alarm_flush_loop 지연 → E2E latency 상승의 주요 원인.
    # 변경: asyncio.create_task()로 백그라운드 실행.
    #       FastAPI는 저장 완료를 기다리지 않고 즉시 Redis 스냅샷·응답 반환으로 진행.
    # 트레이드오프: DRF 저장 실패 시 503/502 대신 로그(logger.warning/error)만 기록됨.
    async def _save_to_drf() -> None:
        await post_to_drf(
            DRF_GAS_PATH,
            drf_payload,
            raise_on_error=False,
            log_category="gas_service",
        )

    asyncio.create_task(_save_to_drf())

    gas_snapshot = {
        "co": payload.co,
        "h2s": payload.h2s,
        "co2": payload.co2,
        "o2": payload.o2,
        "no2": payload.no2,
        "so2": payload.so2,
        "o3": payload.o3,
        "nh3": payload.nh3,
        "voc": payload.voc,
        **individual_risks,
    }
    await store_gas_snapshot(
        gas_snapshot, datetime.now(timezone.utc).isoformat()
    )  # 이성현 수정 — Redis 이관

    logger.debug(
        f"[gas_service] action=processed device={payload.device_id} "
        f"saved_id=async(fire-and-forget)"
    )
    return {
        "received": True,
        "device_id": payload.device_id,
        "status": payload.status,
        **individual_risks,
    }
