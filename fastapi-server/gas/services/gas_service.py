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
from pathlib import Path
from core.config import settings
from services.anomaly_alarm import forward_inference_e2e
from datetime import datetime, timezone

from fastapi import HTTPException

from core.gas_thresholds import calculate_individual_risks
from gas.schemas.gas import GasDataPayload
from services.drf_client import DrfClientError, post_to_drf
from core.metrics import AI_INFERENCE_DURATION, AI_INFERENCE_FAILED_TOTAL, SENSOR_LAST_RECEIVED
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


# 이성현 작업
# co, h2s, co2값을 담아두는 버퍼 , 최대 30개 , 슬라이딩 윈도우 구현에 맞음
_co_window: deque = deque(maxlen=30)
_h2s_window: deque = deque(maxlen=30)
_co2_window: deque = deque(maxlen=30)

# 이성현 추가 — 같은 센서 60초당 1회만 알람 발화 (전력 서비스와 동일 rate limit 패턴)
_gas_last_fired_at: dict[str, float] = {}
GAS_RATE_LIMIT_SEC = 30

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
        try:
            entry = await _get_or_load("gas")
            if entry is None:
                # 모델 미등록 — AI 없이 룰 기반으로만 처리. DRF 저장은 아래 로직으로 계속 진행.
                AI_INFERENCE_FAILED_TOTAL.labels("gas_if", "model_not_loaded").inc()
            # P2 전 — IF 추론 실행 시간 측정
            _infer_start = time.time()
            row = _build_multi_feature_row(
                {
                    "co": list(_co_window),
                    "h2s": list(_h2s_window),
                    "co2": list(_co2_window),
                },
                entry.window,
                arima_results=_arima_models if _arima_models else None,  # 이성현 추가
            )
            pred = int(entry.model.predict(row)[0])
            score = float(entry.model.decision_function(row)[0])
            AI_INFERENCE_DURATION.labels("gas_if").observe(time.time() - _infer_start)

            if pred == -1:  # AI가 이상 패턴으로 판단했을 때만 실행 (-1=이상, 1=정상)
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
                asyncio.create_task(  # 백그라운드 실행 (가스 데이터 저장 흐름을 막지 않기 위해)
                    forward_inference_e2e(  # 팀장 공용 함수: ML결과 저장 + 알람 저장 + 브라우저 전송을 한 번에 처리
                        ml_payload={  # AI 추론 결과 DB 저장용 데이터 (should_fire 무관하게 매번 저장됨)
                            "ml_model": None,  # 모델 FK — 현재 미사용
                            "model_version_snapshot": entry.version,  # 사용된 AI 모델 버전
                            "sensor_type": "gas",  # 센서 종류
                            "sensor_identifier": sensor_identifier,  # 위에서 만든 센서 고유 이름
                            "measured_at": payload.timestamp.isoformat(),  # 측정 시각
                            "anomaly_score": score,  # AI 이상 점수 (음수일수록 더 이상함)
                            "prediction": "anomaly",  # 예측 결과
                            "risk_classified": "danger",  # 위험도 분류
                            "feature_snapshot_json": {  # AI 판단에 사용한 실제 측정값
                                "co": payload.co,
                                "h2s": payload.h2s,
                                "co2": payload.co2,
                            },
                        },
                        alarm_payload={  # 알람 기록 DB 저장용 데이터 (should_fire=True일 때만 저장됨)
                            "alarm_type": "gas_anomaly_ai",  # 알람 종류 — 가스 AI 이상탐지
                            "risk_level": "danger",  # 위험도
                            "source_sensor_id": payload.device_id,  # 어떤 센서에서 발생했는지
                            "gas_type": "co",  # 대표 가스 종류
                            "measured_value": payload.co,  # 대표 측정값
                            "summary": f"가스 이상 감지 (AI) | CO:{payload.co} H2S:{payload.h2s} CO2:{payload.co2}",  # 알람 요약 문자열
                            "detected_at": payload.timestamp.isoformat(),  # 감지 시각
                            "source_label": "가스센서 AI 이상탐지",  # 화면에 표시될 출처 이름
                        },
                        push_payload={  # 브라우저 알람 팝업용 데이터 (should_fire=True일 때만 전송됨)
                            "alarm_type": "gas_anomaly_ai",  # 알람 종류
                            "risk_level": "danger",  # 위험도
                            "source_label": "가스센서 AI 이상탐지",  # 화면 표시용 출처 이름
                            "summary": f"가스 이상 감지 (AI) | CO:{payload.co} H2S:{payload.h2s} CO2:{payload.co2}",  # 팝업에 보여줄 요약
                            "is_new_event": True,  # 새 이벤트 여부
                            "gas_type": "co",  # 대표 가스 종류
                            "measured_value": payload.co,  # 대표 측정값
                        },
                        should_fire=should_fire,  # True면 알람+브라우저 전송, False면 ML결과 DB 기록만
                    )
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
