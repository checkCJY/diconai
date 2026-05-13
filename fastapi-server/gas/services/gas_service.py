# gas/services/gas_service.py — 가스 데이터 처리 서비스
#
# 가스 센서 수신 데이터의 비즈니스 로직을 담당한다.
#   1. DRF에 측정값을 저장한다 (DRF 내부에서 Celery 알람 태스크를 트리거함).
#   2. latest_gas_snapshot을 갱신해 다음 WebSocket 틱에 브라우저로 전달한다.
#
# 알람은 Celery 태스크가 /internal/alarms/push/ 를 통해 직접 active_alarms에 추가한다.
# HTTP Push(/internal/*) 없이 websocket/state.py를 직접 갱신하는 방식을 사용한다.
import logging
from websocket.services.alarm_queue import push_alarm
from datetime import datetime, timezone

from fastapi import HTTPException

from core.gas_thresholds import calculate_individual_risks
from gas.schemas.gas import GasDataPayload
from services.drf_client import DrfClientError, post_to_drf
from websocket.state import gas_latest, latest_gas_snapshot
from collections import (
    deque,
)  # co 값을 최근 30개만 유지하는 버퍼 , 30개 이상 시 오래 된 순으로 자동으로 버림
from ai.router import (
    _get_or_load,
    _build_feature_row,
)  # 학습된 ai모델을 가져옴 , co 값 30개를 ai읽을 수 있는 형태로 변환


logger = logging.getLogger(__name__)

# 이성현 작업
# co 값을 담아두는 버퍼 , 최대 30개 , 슬라이딩 윈도우 구현에 맞음
_co_window: deque = deque(maxlen=30)

DRF_GAS_PATH = "/api/monitoring/gas/"


async def process_gas_data(payload: GasDataPayload) -> dict:
    """
    가스 데이터 수신 후 전체 처리 흐름을 조율한다.

    1. 가스별 위험도(individual_risks)를 계산한다.
    2. DRF에 측정값과 위험도를 저장한다 (DRF → Celery 태스크 → FastAPI /internal/alarms/push/).
    3. latest_gas_snapshot을 갱신해 WebSocket 브로드캐스트에 포함시킨다.

    DRF 통신 실패는 센서 장비에 적절한 HTTP 응답을 돌려주기 위해 예외로 전파한다.
    """
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

    # 이성현 작업 — co 슬라이딩 윈도우 추론
    # _co_window.append(payload.co) — 들어온 co 값을 버퍼에 추가
    # if len(_co_window) >= 30 — 30개 쌓여야 추론 시작 (그 전엔 데이터 부족)
    # entry.model.predict(row)[0] — AI가 판단. -1이면 이상, 1이면 정상
    # logger.warning — 이상 감지 시 로그 출력 (알람 연동은 다음 단계)
    # except — 추론 실패해도 가스 데이터 저장은 계속 진행
    _co_window.append(payload.co)
    if len(_co_window) >= 30:
        try:
            entry = await _get_or_load("gas")
            row = _build_feature_row(list(_co_window), entry.window)
            pred = int(entry.model.predict(row)[0])
            if pred == -1:
                logger.warning(
                    f"[AI 이상탐지] co 이상 감지 | device={payload.device_id} | co={payload.co}"
                )
                await push_alarm(
                    {
                        "alarm_type": "gas_anomaly_ai",  # 알람 종류 식별자. AI 알람임을 구분
                        "risk_level": "danger",  # 위험도
                        "source_label": "가스센서 AI 이상탐지",  # 브라우저에 표시될 출처
                        "summary": f"CO 이상 감지 (AI) | 측정값: {payload.co}",  #  알람 내용
                        "is_new_event": True,
                        "gas_type": "co",
                        "measured_value": payload.co,  # 실제 측정된 co 값
                    }
                )

        except Exception as e:
            logger.error(f"[AI 추론 실패] {e}")

    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": payload.timestamp.isoformat(),
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
