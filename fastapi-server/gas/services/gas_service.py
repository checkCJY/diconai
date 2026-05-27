# gas/services/gas_service.py — 가스 데이터 처리 서비스
#
# 가스 센서 수신 데이터의 비즈니스 로직을 담당한다.
#   1. DRF에 측정값을 저장한다 (DRF 내부에서 Celery 알람 태스크를 트리거함).
#   2. latest_gas_snapshot을 갱신해 다음 WebSocket 틱에 브라우저로 전달한다.
#
# 알람은 Celery 태스크가 /internal/alarms/push/ 를 통해 직접 active_alarms에 추가한다.
# HTTP Push(/internal/*) 없이 websocket/state.py를 직접 갱신하는 방식을 사용한다.
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

from fastapi import HTTPException

from core.gas_thresholds import calculate_individual_risks
from gas.schemas.gas import GasDataPayload
from services.drf_client import DrfClientError, post_to_drf
from core.metrics import (
    AI_INFERENCE_DURATION,
    AI_INFERENCE_FAILED_TOTAL,
    SENSOR_LAST_RECEIVED,
)
from websocket.state import gas_latest, latest_gas_snapshot
from collections import (
    deque,
)  # co 값을 최근 30개만 유지하는 버퍼 , 30개 이상 시 오래 된 순으로 자동으로 버림
from ai.router import (
    _get_or_load,
    _build_multi_feature_row,
)  # 학습된 ai모델을 가져옴 , co 값 30개를 ai읽을 수 있는 형태로 변환


logger = logging.getLogger(__name__)

# 이성현 추가 — ARIMA pkl 모듈 레벨 로드 (실시간 잔차 계산용)
# 이성현 수정 — statsmodels pickle 임포트 버그 대비 try-except 추가 (실패 시 12피처로 폴백)
_arima_models: dict = {}
for _gn in ["co", "h2s", "co2"]:
    _p = Path(settings.ML_MODELS_DIR) / f"arima_{_gn}.pkl"
    if _p.exists():
        try:
            _arima_models[_gn] = joblib.load(_p)["result"]
        except Exception:
            pass


# 이성현 추가 — 슬라이딩 윈도우에서 체인지 포인트 탐지
def _detect_change_point(values: list[float], penalty: float = 3.0) -> bool:
    """30틱 윈도우에서 패턴 전환 시점이 있으면 True 반환."""
    arr = np.array(values, dtype=np.float64).reshape(-1, 1)
    try:
        model = rpt.Pelt(model="rbf").fit(arr)
        result = model.predict(pen=penalty)
        actual_cps = [cp for cp in result if cp < len(arr)]
        return len(actual_cps) > 0
    except Exception:
        return False


# 이성현 작업
# co, h2s, co2값을 담아두는 버퍼 , 최대 30개 , 슬라이딩 윈도우 구현에 맞음
_co_window: deque = deque(maxlen=30)
_h2s_window: deque = deque(maxlen=30)
_co2_window: deque = deque(maxlen=30)

# 이성현 추가 — 같은 센서 60초당 1회만 알람 발화 (전력 서비스와 동일 rate limit 패턴)
# [M-3] 하드코딩 제거 — settings.GAS_AI_RATE_LIMIT_SEC 로 환경별 조정 가능.
# DRF 의 ALARM_REPOPUP_COOLDOWN_SEC 과 값을 맞추려면 .env 에서 함께 변경할 것.
_gas_last_fired_at: dict[str, float] = {}
GAS_RATE_LIMIT_SEC = settings.GAS_AI_RATE_LIMIT_SEC

DRF_GAS_PATH = "/api/monitoring/gas/"


async def process_gas_data(payload: GasDataPayload) -> dict:
    """
    가스 데이터 수신 후 전체 처리 흐름을 조율한다.

    1. 가스별 위험도(individual_risks)를 계산한다.
    2. DRF에 측정값과 위험도를 저장한다 (DRF → Celery 태스크 → FastAPI /internal/alarms/push/).
    3. latest_gas_snapshot을 갱신해 WebSocket 브로드캐스트에 포함시킨다.

    DRF 통신 실패는 센서 장비에 적절한 HTTP 응답을 돌려주기 위해 예외로 전파한다.
    """
    # P1 — 센서 마지막 수신 시각 갱신. 5분 이상 갱신 없으면 통신 이상으로 판단.
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

    # 이성현 수정 — co 단변량 → co + h2s + co2 다변량 슬라이딩 윈도우 추론
    _co_window.append(payload.co)
    _h2s_window.append(payload.h2s)
    _co2_window.append(payload.co2)
    if len(_co_window) >= 30:
        # 이성현 추가 — 체인지 포인트 탐지 (패턴 변화 없으면 추론 스킵)
        cp_detected = (
            _detect_change_point(list(_co_window))
            or _detect_change_point(list(_h2s_window))
            or _detect_change_point(list(_co2_window))
        )
        if not cp_detected:
            logger.debug("[체인지 포인트] 패턴 변화 없음 — 추론 스킵")
        else:
            logger.debug("[체인지 포인트] 패턴 변화 감지 — IF 추론 진행")
            try:
                # 이성현 수정 — sensor_identifier 를 train_anomaly_model 저장 포맷에 맞게 전달 (gas:sensor_{pk}:{gas_label})
                _model_identifier = "gas:sensor_1:co_h2s_co2"
                entry = await _get_or_load("gas", sensor_identifier=_model_identifier)
                if entry is None:
                    # 모델 미등록 — AI 없이 룰 기반으로만 처리. DRF 저장은 아래 로직으로 계속 진행.
                    AI_INFERENCE_FAILED_TOTAL.labels("gas_if", "model_not_loaded").inc()
                    raise RuntimeError("gas IF 모델 미등록")
                # P2 전 — IF 추론 실행 시간 측정
                _infer_start = time.time()
                row = _build_multi_feature_row(
                    {
                        "co": list(_co_window),
                        "h2s": list(_h2s_window),
                        "co2": list(_co2_window),
                    },
                    entry.window,
                    arima_results=_arima_models
                    if _arima_models
                    else None,  # 이성현 추가
                )
                pred = int(entry.model.predict(row)[0])
                score = float(entry.model.decision_function(row)[0])
                AI_INFERENCE_DURATION.labels("gas_if").observe(
                    time.time() - _infer_start
                )

                if (
                    pred == -1
                ):  # AI가 이상 패턴으로 판단했을 때만 실행 (-1=이상, 1=정상)
                    # 이성현 수정 — should_fire=True 하드코딩 제거, 60초 rate limit 적용
                    sensor_identifier = f"gas:{payload.device_id}:co_h2s_co2"  # 이 센서만의 고유 이름 (장치ID + 가스 종류 조합)
                    now_ts = time.time()  # 지금 이 순간의 시각 (초 단위 숫자)
                    last_ts = _gas_last_fired_at.get(
                        sensor_identifier, 0.0
                    )  # 이 센서가 마지막으로 알람을 쐈던 시각 (처음이면 0.0)
                    should_fire = (
                        (now_ts - last_ts) >= GAS_RATE_LIMIT_SEC
                    )  # 마지막 알람 후 60초 이상 지났으면 True, 아니면 False
                    if should_fire:  # 60초가 지났을 때만 실행
                        _gas_last_fired_at[sensor_identifier] = (
                            now_ts  # 방금 쏜 시각 기록 (다음 번 비교에 사용)
                        )
                        logger.warning(  # 서버 로그에 이상 감지 출력 (60초 지났을 때만)
                            f"[AI 이상탐지] co+h2s+co2 이상 감지 | device={payload.device_id} | co={payload.co} h2s={payload.h2s} co2={payload.co2}"
                        )
                        # DRF gas_alarm 가드용 mute 마킹 — 추론 가스 3종에 한해 룰 60s 억제.
                        # sensor_id 자리에 payload.device_id (mac) — DRF gas_alarm 측은
                        # sensor.device_name (mac) 으로 동일 키 read.
                        for _g in ("co", "h2s", "co2"):
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
                    # 이성현 수정 — forward_inference_e2e 시그니처에 맞게 수정 (push_payload/should_fire 제거)
                    # ML결과 저장은 매번, alarm_payload는 should_fire=True일 때만 전달
                    # [M-2 수정] create_task 미처리 예외가 "Task exception was never retrieved"
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
                                "feature_snapshot_json": {
                                    "co": payload.co,
                                    "h2s": payload.h2s,
                                    "co2": payload.co2,
                                },
                            },
                            alarm_payload={  # should_fire=True일 때만 AlarmRecord 저장
                                "alarm_type": "gas_anomaly_ai",
                                "risk_level": "danger",
                                "source_sensor_id": payload.device_id,
                                "gas_type": "co",
                                "measured_value": payload.co,
                                "summary": f"가스 이상 감지 (AI) | CO:{payload.co} H2S:{payload.h2s} CO2:{payload.co2}",
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
                        _p = asyncio.create_task(
                            push_alarm(
                                {
                                    "alarm_type": "gas_anomaly_ai",
                                    "risk_level": "danger",
                                    "source_label": "가스센서 AI 이상탐지",
                                    "summary": f"가스 이상 감지 (AI) | CO:{payload.co} H2S:{payload.h2s} CO2:{payload.co2}",
                                    "message": f"가스 이상 감지 (AI) | CO:{payload.co} H2S:{payload.h2s} CO2:{payload.co2}",
                                    "is_new_event": True,
                                    "gas_type": "co",
                                    "measured_value": payload.co,
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

    try:
        res = await post_to_drf(
            DRF_GAS_PATH,
            drf_payload,
            raise_on_error=True,
            log_category="gas_service",
        )
    except DrfClientError as exc:
        # 통신 실패는 503, 4xx는 그대로, 그 외 비성공은 502로 매핑.
        if exc.status is None:
            raise HTTPException(status_code=503, detail=exc.detail) from exc
        if exc.status == 404:
            raise HTTPException(
                status_code=404, detail="등록되지 않은 장치입니다."
            ) from exc
        raise HTTPException(
            status_code=502, detail="데이터 저장에 실패했습니다."
        ) from exc

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
    latest_gas_snapshot.update(gas_snapshot)
    gas_latest["updated_at"] = datetime.now(timezone.utc).isoformat()

    logger.debug(
        f"[gas_service] action=processed device={payload.device_id} "
        f"saved_id={res.json().get('id') if res else '?'}"
    )
    return {
        "received": True,
        "device_id": payload.device_id,
        "status": payload.status,
        **individual_risks,
    }
