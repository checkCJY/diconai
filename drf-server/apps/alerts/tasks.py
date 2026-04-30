# alerts/tasks.py — 가스 알람 Celery 태스크
#
# 3종 알람 태스크:
#   fire_danger_alarm_task  : DANGER 즉각 알람 (gas_alarm.py가 즉시 실행)
#   fire_warning_alarm_task : WARNING 30초 지속 후 알람 (countdown=30으로 지연 실행)
#   fire_clear_notification_task : 정상화 알림 (gas_alarm.py가 즉시 실행)
#
# 각 태스크는 AlarmRecord/Event를 DB에 기록한 뒤,
# FastAPI /internal/alarms/push/ 엔드포인트로 WebSocket 브로드캐스트 큐에 알람을 추가한다.
import logging

import httpx
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# WARNING 타이머 (gas_alarm.py의 countdown 값과 반드시 일치해야 함)
WARNING_DURATION_SEC = 30

# FastAPI 내부 알람 푸시 엔드포인트
FASTAPI_INTERNAL_URL = "http://127.0.0.1:8001/internal/alarms/push/"

# 가스 종류별 한글 표시명
_GAS_NAME = {
    "co":  "CO (일산화탄소)",
    "h2s": "H₂S (황화수소)",
    "co2": "CO₂ (이산화탄소)",
    "o2":  "O₂ (산소)",
    "no2": "NO₂ (이산화질소)",
    "so2": "SO₂ (이산화황)",
    "o3":  "O₃ (오존)",
    "nh3": "NH₃ (암모니아)",
    "voc": "VOC (휘발성유기화합물)",
}


def _push_to_ws(alarm_data: dict) -> None:
    """FastAPI WebSocket 브로드캐스트 큐에 알람을 추가한다.

    실패해도 태스크 자체는 성공으로 처리 — DB 기록이 우선이고
    WS 알림 누락은 다음 틱에서 Event 목록으로 확인 가능.
    """
    try:
        httpx.post(FASTAPI_INTERNAL_URL, json=alarm_data, timeout=3.0)
    except Exception as e:
        logger.warning("FastAPI WS 알람 푸시 실패 (WS 알림 누락): %s", e)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_danger_alarm_task(
    self,
    sensor_id: int,
    gas_type: str,
    value: float,
    facility_id: int,
    source_label: str,
):
    """DANGER 즉각 알람 — AlarmRecord/Event 생성 후 FastAPI WS 큐에 푸시."""
    from apps.alerts.services.event_service import create_alarm_and_event
    from apps.core.constants import AlarmType
    from apps.monitoring.utils.gas_thresholds import GAS_UNITS, get_threshold_value

    try:
        gas_name  = _GAS_NAME.get(gas_type, gas_type.upper())
        unit      = GAS_UNITS.get(gas_type, "")
        threshold = get_threshold_value(gas_type, "danger")
        summary   = (
            f"[긴급] {gas_name} 위험 수준 초과 ({value} {unit})"
            " — 즉시 대피하고 관리자에게 보고하세요."
        )

        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.GAS_THRESHOLD,
            sensor_id=sensor_id,
            gas_type=gas_type,
            measured_value=value,
            threshold_value=threshold,
            risk_level="danger",
            source_label=source_label,
            summary=summary,
            detected_at=timezone.now(),
        )

        if event is not None:
            _push_to_ws({
                "event_id":        event.id,
                "alarm_type":      AlarmType.GAS_THRESHOLD,
                "gas_type":        gas_type,
                "risk_level":      "danger",
                "measured_value":  value,
                "threshold_value": threshold,
                "source_label":    source_label,
                "summary":         summary,
                "is_new_event":    alarm is not None,
            })
            logger.info("DANGER 알람 푸시 | sensor=%s gas=%s value=%s new_event=%s", sensor_id, gas_type, value, alarm is not None)

    except Exception as exc:
        logger.error("DANGER 알람 생성 실패: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_warning_alarm_task(
    self,
    sensor_id: int,
    gas_type: str,
    value: float,
    facility_id: int,
    source_label: str,
):
    """WARNING 30초 지속 후 알람 — AlarmRecord/Event 생성 후 FastAPI WS 큐에 푸시.

    gas_alarm.py에서 apply_async(countdown=WARNING_DURATION_SEC)로 호출되므로
    이 태스크가 실행될 시점에는 이미 30초가 경과한 상태.
    """
    from apps.alerts.services.event_service import create_alarm_and_event
    from apps.core.constants import AlarmType
    from apps.monitoring.utils.gas_thresholds import GAS_UNITS, get_threshold_value

    try:
        gas_name  = _GAS_NAME.get(gas_type, gas_type.upper())
        unit      = GAS_UNITS.get(gas_type, "")
        threshold = get_threshold_value(gas_type, "warning")
        summary   = (
            f"[주의] {gas_name} 주의 수준 {WARNING_DURATION_SEC}초 지속 ({value} {unit})"
            " — 작업을 중단하고 환기 후 관리자에게 보고하세요."
        )

        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.GAS_THRESHOLD,
            sensor_id=sensor_id,
            gas_type=gas_type,
            measured_value=value,
            threshold_value=threshold,
            risk_level="warning",
            source_label=source_label,
            summary=summary,
            detected_at=timezone.now(),
        )

        if event is not None:
            _push_to_ws({
                "event_id":        event.id,
                "alarm_type":      AlarmType.GAS_THRESHOLD,
                "gas_type":        gas_type,
                "risk_level":      "warning",
                "measured_value":  value,
                "threshold_value": threshold,
                "source_label":    source_label,
                "summary":         summary,
                "is_new_event":    alarm is not None,
            })
            logger.info("WARNING 알람 푸시 | sensor=%s gas=%s value=%s new_event=%s", sensor_id, gas_type, value, alarm is not None)

    except Exception as exc:
        logger.error("WARNING 알람 생성 실패: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_clear_notification_task(
    self,
    sensor_id: int,
    source_label: str,
    gas_type: str,
):
    """정상화 알림 — 가스 농도 복귀 시 WS 알림만 발송. 이벤트 상태는 운영자가 직접 변경."""
    try:
        gas_name = _GAS_NAME.get(gas_type, gas_type.upper())
        summary  = (
            f"[안전] {source_label} — {gas_name} 농도가 정상 범위로 복귀했습니다."
            " 관리자 확인 후 작업을 재개하세요."
        )

        _push_to_ws({
            "alarm_type":   "gas_clear",
            "gas_type":     gas_type,
            "risk_level":   "normal",
            "source_label": source_label,
            "summary":      summary,
            "is_new_event": False,
        })
        logger.info("정상화 알림 발송 | sensor=%s gas=%s", sensor_id, gas_type)

    except Exception as exc:
        logger.error("정상화 알림 실패: %s", exc)
        raise self.retry(exc=exc)
