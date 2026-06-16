# power/services/power_service.py — 전력 데이터 수신·송출 진입 façade
#
# 데이터 흐름:
#   IN  : power_router (FastAPI) — 채널별 측정 페이로드 (watt/current/voltage/onoff)
#   OUT : 1) DRF HTTP POST — PowerData / PowerEvent 영속화 (fire-and-forget)
#         2) Redis snap_store — 채널별 dict 갱신 (broadcast_loop 가 읽음)
#         3) AI 추론 분기 → anomaly_inference.process_anomaly_inference
#
# 본 모듈은 진입 façade — 실제 로직은 도메인별 서비스 모듈로 분리:
#   · anomaly_inference  : AI 추론 + 알람 결정
#   · equipment_builder  : WebSocket equipment[] 조립
#   · zscore_anomaly     : Z-score 통계 이상 + 윈도우
#   · night_escalation   : KST 야간 격상 게이트
from datetime import datetime, timezone

from power.services.anomaly_inference import process_anomaly_inference
from power.services.equipment_builder import build_equipment
from power.services.night_escalation import _is_night_kst_iso
from power.services.zscore_anomaly import _INFERENCE_WINDOW, _zscore_check
from services.drf_client import post_to_drf
from websocket.snap_store import store_power_snapshot

__all__ = [
    "DRF_POWER_DATA_PATH",
    "DRF_POWER_EVENT_PATH",
    "build_equipment",
    "now_utc_iso",
    "post_power_to_drf",
    "process_anomaly_inference",
    "to_channel_list",
    "update_power_state",
    # 테스트 호환 (내부 헬퍼 노출):
    "_INFERENCE_WINDOW",
    "_is_night_kst_iso",
    "_zscore_check",
]

DRF_POWER_EVENT_PATH = "/api/monitoring/power/event/"
DRF_POWER_DATA_PATH = "/api/monitoring/power/data/"


def now_utc_iso() -> str:
    """현재 UTC 시각을 ISO 8601 문자열로 반환한다."""
    return datetime.now(timezone.utc).isoformat()


async def post_power_to_drf(path: str, payload: dict) -> None:
    """전력 데이터를 DRF 에 비동기 fire-and-forget 전송한다.

    BackgroundTask 에서 실행되므로 실패해도 WebSocket 흐름을 블로킹하지 않는다.
    실패는 services.drf_client 가 logger.warning/error 로 기록한다.
    """
    await post_to_drf(path, payload, raise_on_error=False, log_category="power_service")


def to_channel_list(
    channel_values: dict, anomaly_map: dict | None = None
) -> list[dict]:
    """채널별 측정값 dict 를 DRF PowerData 저장 형식 (list[dict]) 으로 변환한다.

    값이 None 인 채널은 통신 불능 (comm_failure) 으로 표시.

    Args:
        channel_values: {채널 int → 측정값 float|None}.
        anomaly_map: {채널 int → anomaly_type str} — 더미 시뮬레이터에서만 채워짐.
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


async def update_power_state(data_type: str, values: dict, measured_at: str) -> None:
    # 이성현 수정 — 프로세스 메모리(power_latest) → Redis(snap_store) 이관
    """전력 스냅샷을 Redis에 갱신한다.

    갱신된 값은 다음 WebSocket 틱에서 broadcast가 Redis를 읽어 브라우저로 전달된다.
    """
    await store_power_snapshot(data_type, values, measured_at)
