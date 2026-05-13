# gas/services/gas_service.py — 가스 데이터 처리 서비스
#
# 가스 센서 수신 데이터의 비즈니스 로직을 담당한다.
#   1. DRF에 측정값을 저장한다 (DRF 내부에서 Celery 알람 태스크를 트리거함).
#   2. latest_gas_snapshot을 갱신해 다음 WebSocket 틱에 브라우저로 전달한다.
#
# 알람은 Celery 태스크가 /internal/alarms/push/ 를 통해 직접 active_alarms에 추가한다.
# HTTP Push(/internal/*) 없이 websocket/state.py를 직접 갱신하는 방식을 사용한다.
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from core.gas_thresholds import calculate_individual_risks
from gas.schemas.gas import GasDataPayload
from services.drf_client import DrfClientError, post_to_drf
from websocket.state import gas_latest, latest_gas_snapshot

logger = logging.getLogger(__name__)

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
