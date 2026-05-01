# alerts/services/event_service.py

from django.db import transaction
from apps.alerts.models import Event, AlarmRecord, EventLog
from apps.core.constants import EventStatus, RiskLevel
from django.utils import timezone

from datetime import timedelta

RISK_LEVELS = ["normal", "warning", "danger"]
RENOTIFY_COOLDOWN_MINUTES = 5


# 알람발생 시, Event 생성/병합 플로우
@transaction.atomic
def create_alarm_and_event(
    facility_id: int,
    alarm_type: str,
    sensor_id: int = None,
    power_device_id: int = None,
    geofence_id: int = None,
    worker_id: int = None,
    gas_type: str = "",
    measured_value: float = None,
    threshold_value: float = None,
    risk_level: str = RiskLevel.WARNING,
    source_label: str = "",
    summary: str = "",
    detected_at=None,
):
    """
    AlarmRecord + Event 생성/병합 핵심 로직

    1. 병합 대상 활성 Event 검색 (select_for_update)
    2. 존재: AlarmRecord만 생성, Event 업데이트
    3. 없음: Event 생성 + AlarmRecord 생성 + EventLog(CREATED)
    """
    # 활성 Event 조회 (레이스 컨디션 방지 select_for_update)
    event_qs = Event.objects.select_for_update().filter(
        facility_id=facility_id,
        event_type=alarm_type,
        status__in=[
            EventStatus.ACTIVE,
            EventStatus.ACKNOWLEDGED,
            EventStatus.IN_PROGRESS,
        ],
    )
    if sensor_id:
        event_qs = event_qs.filter(source_sensor_id=sensor_id)
    elif power_device_id:
        event_qs = event_qs.filter(source_power_device_id=power_device_id)
    elif geofence_id:
        event_qs = event_qs.filter(source_geofence_id=geofence_id)

    active_event = event_qs.first()

    if active_event:
        # 🚨 [추가된 로직] 타임 윈도우 검사 (무한 병합 방지)
        if not active_event.is_mergeable_time_window:
            previous_status = active_event.status
            # 기존 이벤트를 강제로 완료 처리 (쿼리에서 다시 잡히지 않도록 상태 변경)
            active_event.status = EventStatus.RESOLVED
            active_event.save(update_fields=["status"])

            # 시스템에 의한 자동 분리 로그 기록
            EventLog.objects.create(
                event=active_event,
                action=EventLog.Action.RESOLVED,
                previous_status=previous_status,
                new_status=EventStatus.RESOLVED,
                note="최대 병합 시간 초과로 인한 자동 분리 및 종료",
            )
            # 활성 이벤트를 None으로 초기화하여 아래쪽의 '새 Event 생성' 로직으로 넘김
            active_event = None

        else:
            # ✅ [기존 로직] 정상 병합 (타임 윈도우 이내)
            alarm = AlarmRecord.objects.create(
                facility_id=facility_id,
                event=active_event,
                alarm_type=alarm_type,
                sensor_id=sensor_id,
                power_device_id=power_device_id,
                geofence_id=geofence_id,
                worker_id=worker_id,
                gas_type=gas_type,
                measured_value=measured_value,
                threshold_value=threshold_value,
                risk_level=risk_level,
            )
            active_event.last_detected_at = detected_at
            # 위험도 상승 시 Event risk_level 업데이트
            if RISK_LEVELS.index(risk_level) > RISK_LEVELS.index(
                active_event.risk_level
            ):
                active_event.risk_level = risk_level

            # 쿨다운 초과 시 재알림: last_notified_at 갱신 후 alarm 반환
            cooldown = timedelta(minutes=RENOTIFY_COOLDOWN_MINUTES)
            needs_renotify = (
                active_event.last_notified_at is None
                or (timezone.now() - active_event.last_notified_at) >= cooldown
            )
            if needs_renotify:
                active_event.last_notified_at = timezone.now()
                active_event.save(
                    update_fields=["last_detected_at", "risk_level", "last_notified_at"]
                )
                return active_event, alarm  # 재알림 발송

            active_event.save(update_fields=["last_detected_at", "risk_level"])
            return active_event, None  # 쿨다운 이내 — 재발송 안 함

    # 새 Event 생성 (활성 이벤트가 없거나, 타임 윈도우 초과로 강제 분리된 경우 실행됨)
    if not active_event:
        event = Event.objects.create(
            facility_id=facility_id,
            event_type=alarm_type,
            risk_level=risk_level,
            status=EventStatus.ACTIVE,
            source_sensor_id=sensor_id,
            source_power_device_id=power_device_id,
            source_geofence_id=geofence_id,
            worker_id=worker_id,
            source_label=source_label,
            summary=summary,
            first_detected_at=detected_at,
            last_detected_at=detected_at,
            last_notified_at=timezone.now(),
        )
        alarm = AlarmRecord.objects.create(
            facility_id=facility_id,
            event=event,
            alarm_type=alarm_type,
            sensor_id=sensor_id,
            power_device_id=power_device_id,
            geofence_id=geofence_id,
            worker_id=worker_id,
            gas_type=gas_type,
            measured_value=measured_value,
            threshold_value=threshold_value,
            risk_level=risk_level,
        )
        EventLog.objects.create(
            event=event,
            action=EventLog.Action.CREATED,
            new_status=EventStatus.ACTIVE,
        )
        return event, alarm  # 새 Event는 Notification 발송


# 관리자 이벤트 확인 플로우
def acknowledge_event(event_id: int, actor_user_id: int, note: str = ""):
    """관리자가 이벤트 확인 처리"""
    event = Event.objects.select_for_update().get(pk=event_id)

    if event.status != EventStatus.ACTIVE:
        raise ValueError(f"ACTIVE 상태에서만 확인 가능: 현재 {event.status}")

    previous = event.status
    event.status = EventStatus.ACKNOWLEDGED
    event.acknowledged_by_id = actor_user_id
    event.acknowledged_at = timezone.now()
    event.save(update_fields=["status", "acknowledged_by", "acknowledged_at"])

    EventLog.objects.create(
        event=event,
        actor_id=actor_user_id,
        action=EventLog.Action.CONFIRMED,
        previous_status=previous,
        new_status=EventStatus.ACKNOWLEDGED,
        note=note,
    )
