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

# WARNING 타이머 — gas_alarm.py / power_alarm.py가 import해서 사용하므로
# 이 값만 바꾸면 두 도메인의 countdown이 함께 변경된다.
WARNING_DURATION_SEC = 10

# FastAPI 내부 알람 푸시 엔드포인트
FASTAPI_INTERNAL_URL = "http://127.0.0.1:8001/internal/alarms/push/"

# 가스 종류별 한글 표시명
_GAS_NAME = {
    "co": "CO (일산화탄소)",
    "h2s": "H₂S (황화수소)",
    "co2": "CO₂ (이산화탄소)",
    "o2": "O₂ (산소)",
    "no2": "NO₂ (이산화질소)",
    "so2": "SO₂ (이산화황)",
    "o3": "O₃ (오존)",
    "nh3": "NH₃ (암모니아)",
    "voc": "VOC (휘발성유기화합물)",
}


def _push_to_ws(alarm_data: dict) -> None:
    """FastAPI WebSocket 브로드캐스트 큐에 알람을 추가한다.

    실패해도 태스크 자체는 성공으로 처리 — DB 기록이 우선이고
    WS 알림 누락은 다음 틱에서 Event 목록으로 확인 가능.

    [IntegrationLog 기록 — Phase 2-e]
    호출 결과(성공/실패)를 IntegrationLog ORM 직접 INSERT로 영속화.
    fire-and-forget 정책: 기록 실패해도 본 흐름 비차단.
    """
    result = "success"
    try:
        httpx.post(FASTAPI_INTERNAL_URL, json=alarm_data, timeout=3.0)
    except Exception as e:
        logger.warning("FastAPI WS 알람 푸시 실패 (WS 알림 누락): %s", e)
        result = "failure"

    try:
        from apps.operations.models import IntegrationLog

        IntegrationLog.objects.create(
            integration_type=IntegrationLog.IntegrationType.TRANSMIT,
            target_system="DRF→FastAPI",
            result=result,
            description=f"alarm_type={alarm_data.get('alarm_type', '')}",
        )
    except Exception:
        pass  # silent fail — 본 흐름 비차단


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
        gas_name = _GAS_NAME.get(gas_type, gas_type.upper())
        unit = GAS_UNITS.get(gas_type, "")
        threshold = get_threshold_value(gas_type, "danger")
        summary = (
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
            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": AlarmType.GAS_THRESHOLD,
                    "gas_type": gas_type,
                    "risk_level": "danger",
                    "measured_value": value,
                    "threshold_value": threshold,
                    "source_label": source_label,
                    "summary": summary,
                    "is_new_event": alarm is not None,
                }
            )
            logger.info(
                "DANGER 알람 푸시 | sensor=%s gas=%s value=%s new_event=%s",
                sensor_id,
                gas_type,
                value,
                alarm is not None,
            )

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
        gas_name = _GAS_NAME.get(gas_type, gas_type.upper())
        unit = GAS_UNITS.get(gas_type, "")
        threshold = get_threshold_value(gas_type, "warning")
        summary = (
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
            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": AlarmType.GAS_THRESHOLD,
                    "gas_type": gas_type,
                    "risk_level": "warning",
                    "measured_value": value,
                    "threshold_value": threshold,
                    "source_label": source_label,
                    "summary": summary,
                    "is_new_event": alarm is not None,
                }
            )
            logger.info(
                "WARNING 알람 푸시 | sensor=%s gas=%s value=%s new_event=%s",
                sensor_id,
                gas_type,
                value,
                alarm is not None,
            )

    except Exception as exc:
        logger.error("WARNING 알람 생성 실패: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_geofence_alarm_task(
    self,
    worker_id: int,
    facility_id: int,
    geofence_id: int,
    geofence_name: str,
    risk_level: str,
    sensor_source_label: str,
):
    """위험구역 진입 알람 — AlarmRecord/Event 생성 후 FastAPI WS 큐에 푸시."""
    from apps.alerts.services.event_service import create_alarm_and_event
    from apps.core.constants import AlarmType

    label = {"danger": "긴급", "warning": "주의"}.get(risk_level, "")
    summary = (
        f"[{label}] 작업자가 위험구역 '{geofence_name}'에 진입했습니다."
        f" ({sensor_source_label} 임계치 초과)"
    )

    try:
        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.GEOFENCE_INTRUSION,
            geofence_id=geofence_id,
            worker_id=worker_id,
            risk_level=risk_level,
            source_label=geofence_name,
            summary=summary,
            detected_at=timezone.now(),
        )
        if event is not None:
            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": AlarmType.GEOFENCE_INTRUSION,
                    "risk_level": risk_level,
                    "source_label": geofence_name,
                    "summary": summary,
                    "is_new_event": alarm is not None,
                }
            )
            logger.info(
                "지오펜스 알람 푸시 | geofence=%s worker=%s risk=%s new_event=%s",
                geofence_name,
                worker_id,
                risk_level,
                alarm is not None,
            )
    except Exception as exc:
        logger.error("지오펜스 알람 생성 실패: %s", exc)
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
        summary = (
            f"[안전] {source_label} — {gas_name} 농도가 정상 범위로 복귀했습니다."
            " 관리자 확인 후 작업을 재개하세요."
        )

        _push_to_ws(
            {
                "alarm_type": "gas_clear",
                "gas_type": gas_type,
                "risk_level": "normal",
                "source_label": source_label,
                "summary": summary,
                "is_new_event": False,
            }
        )
        logger.info("정상화 알림 발송 | sensor=%s gas=%s", sensor_id, gas_type)

    except Exception as exc:
        logger.error("정상화 알림 실패: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_power_danger_task(
    self,
    device_id: int,
    channel: int,
    value: float,
    facility_id: int,
    source_label: str,
):
    """전력 DANGER 즉각 알람 — AlarmRecord/Event 생성 후 FastAPI WS 큐에 푸시."""
    from apps.alerts.services.event_service import create_alarm_and_event
    from apps.core.constants import AlarmType, POWER_THRESHOLDS

    try:
        threshold = POWER_THRESHOLDS["danger"]
        summary = (
            f"[긴급] {source_label} 전력 과부하 ({value}W)"
            " — 즉시 확인하고 관리자에게 보고하세요."
        )
        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.POWER_OVERLOAD,
            power_device_id=device_id,
            measured_value=value,
            threshold_value=threshold,
            risk_level="danger",
            source_label=source_label,
            summary=summary,
            detected_at=timezone.now(),
        )
        if event is not None:
            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": AlarmType.POWER_OVERLOAD,
                    "channel": channel,
                    "risk_level": "danger",
                    "measured_value": value,
                    "threshold_value": threshold,
                    "source_label": source_label,
                    "summary": summary,
                    "is_new_event": alarm is not None,
                }
            )
            logger.info(
                "전력 DANGER 알람 | device=%s ch=%s value=%sW new_event=%s",
                device_id,
                channel,
                value,
                alarm is not None,
            )
    except Exception as exc:
        logger.error("전력 DANGER 알람 생성 실패: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_power_warning_task(
    self,
    device_id: int,
    channel: int,
    value: float,
    facility_id: int,
    source_label: str,
):
    """전력 WARNING 30초 지속 후 알람 — AlarmRecord/Event 생성 후 FastAPI WS 큐에 푸시."""
    from apps.alerts.services.event_service import create_alarm_and_event
    from apps.core.constants import AlarmType, POWER_THRESHOLDS

    try:
        threshold = POWER_THRESHOLDS["caution"]
        summary = (
            f"[주의] {source_label} 전력 경고 수준 {WARNING_DURATION_SEC}초 지속 ({value}W)"
            " — 설비 상태를 확인하세요."
        )
        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.POWER_OVERLOAD,
            power_device_id=device_id,
            measured_value=value,
            threshold_value=threshold,
            risk_level="warning",
            source_label=source_label,
            summary=summary,
            detected_at=timezone.now(),
        )
        if event is not None:
            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": AlarmType.POWER_OVERLOAD,
                    "channel": channel,
                    "risk_level": "warning",
                    "measured_value": value,
                    "threshold_value": threshold,
                    "source_label": source_label,
                    "summary": summary,
                    "is_new_event": alarm is not None,
                }
            )
            logger.info(
                "전력 WARNING 알람 | device=%s ch=%s value=%sW new_event=%s",
                device_id,
                channel,
                value,
                alarm is not None,
            )
    except Exception as exc:
        logger.error("전력 WARNING 알람 생성 실패: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_power_clear_task(
    self,
    device_id: int,
    channel: int,
    source_label: str,
):
    """전력 정상화 알림 — WS 알림만 발송. 이벤트 상태는 운영자가 직접 변경."""
    try:
        summary = (
            f"[안전] {source_label} — 전력이 정상 범위로 복귀했습니다."
            " 관리자 확인 후 작업을 재개하세요."
        )
        _push_to_ws(
            {
                "alarm_type": "power_clear",
                "channel": channel,
                "risk_level": "normal",
                "source_label": source_label,
                "summary": summary,
                "is_new_event": False,
            }
        )
        logger.info("전력 정상화 알림 | device=%s ch=%s", device_id, channel)
    except Exception as exc:
        logger.error("전력 정상화 알림 실패: %s", exc)
        raise self.retry(exc=exc)
