# alerts/services/event_service.py

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.alerts.models import AlarmRecord, Event, EventLog
from apps.core.constants import EventStatus, RiskLevel

RISK_LEVELS = ["normal", "warning", "danger"]


def _notify_safe(event) -> None:
    """notify_event_created를 안전하게 호출하는 래퍼.

    on_commit 콜백으로 사용되므로 예외가 발생해도 알람 트랜잭션에 영향을 주지 않는다.
    Notification 생성 실패는 알람 저장보다 중요도가 낮으므로 에러 로그만 남기고 계속 진행한다.
    """
    import logging
    from apps.notifications.services.notification_service import notify_event_created

    logger = logging.getLogger(__name__)
    try:
        notify_event_created(event)
    except Exception as exc:
        logger.error(
            f"[notify_event_created] event_id={event.id} 알림 생성 실패: {exc}"
        )


# 재푸시 cooldown 은 settings.ALARM_REPOPUP_COOLDOWN_SEC 에서 주입 — 운영 60s /
# 시연 15s 로 분기 가능. 가스/전력 dedup TTL (monitoring._CACHE_TTL) 과의 일관성은
# 운영 측에서 env 정렬로 유지한다.


# 알람 발생 시 Event 생성/병합 플로우
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
    channel: int = None,
    algorithm_source: str = "",
    source: str = "",
):
    """AlarmRecord + Event 를 생성하거나 활성 Event 에 병합한다.

    1. 병합 대상 활성 Event 검색 (select_for_update)
    2. 존재: AlarmRecord만 생성, Event 업데이트
    3. 없음: Event 생성 + AlarmRecord 생성 + EventLog(CREATED)

    동시성: select_for_update 로 동일 facility 동시 생성 race 방지.
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
        # 타임 윈도우 검사 — 너무 오래된 활성 Event 와의 무한 병합 방지.
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
            # 정상 병합 (타임 윈도우 이내) — 기존 Event 에 AlarmRecord 만 추가.
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
                channel=channel,
                algorithm_source=algorithm_source,
                source=source,
            )
            active_event.last_detected_at = detected_at
            # 위험도 상승(WARNING → DANGER) 시 Event risk_level 업데이트 + EventLog
            # 기록 — 사고 소급 분석에서 이 상태 변화 구간이 공백이 되지 않게.
            risk_escalated = RISK_LEVELS.index(risk_level) > RISK_LEVELS.index(
                active_event.risk_level
            )
            if risk_escalated:
                prev_risk = active_event.risk_level
                active_event.risk_level = risk_level
                EventLog.objects.create(
                    event=active_event,
                    action=EventLog.Action.STATUS_CHANGED,
                    previous_status=active_event.status,
                    new_status=active_event.status,
                    note=f"위험도 상승: {prev_risk} → {risk_level}",
                )

            # 쿨다운 초과 시 재알림. 위험도 상승은 cooldown 무시 (격상 즉시 알림 — escalation).
            cooldown = timedelta(seconds=settings.ALARM_REPOPUP_COOLDOWN_SEC)
            needs_renotify = (
                risk_escalated
                or active_event.last_notified_at is None
                or (timezone.now() - active_event.last_notified_at) >= cooldown
            )
            if needs_renotify:
                active_event.last_notified_at = timezone.now()
                active_event.save(
                    update_fields=["last_detected_at", "risk_level", "last_notified_at"]
                )
                # 재알림 발송 시 Notification 생성. on_commit 으로 트랜잭션 커밋 후
                # 호출 — 롤백될 수 있는 Event 를 Notification 이 참조하는 상황 방지.
                _event_ref = active_event
                transaction.on_commit(lambda: _notify_safe(_event_ref))
                return active_event, alarm  # 재알림 발송

            active_event.save(update_fields=["last_detected_at", "risk_level"])
            return active_event, None  # 쿨다운 이내 — 재발송 안 함

    # 새 Event 생성 (활성 이벤트가 없거나, 타임 윈도우 초과로 강제 분리된 경우 실행됨)
    if not active_event:
        # AlertPolicy 자동 매칭 → Event.policy FK 채움
        from apps.alerts.services.policy_matcher import match_policy

        policy = match_policy(
            event_type=alarm_type,
            facility_id=facility_id,
            sensor_id=sensor_id,
            device_id=power_device_id,
            geofence_id=geofence_id,
        )

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
            policy=policy,
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
            channel=channel,
            algorithm_source=algorithm_source,
            source=source,
        )
        EventLog.objects.create(
            event=event,
            action=EventLog.Action.CREATED,
            new_status=EventStatus.ACTIVE,
        )
        # 신규 Event 생성 시 Notification 생성. on_commit 으로 트랜잭션 커밋 후
        # 호출 — 롤백될 수 있는 Event 를 Notification 이 참조하는 상황 방지.
        _event_ref = event
        transaction.on_commit(lambda: _notify_safe(_event_ref))
        return event, alarm  # 새 Event는 Notification 발송


# 관리자 이벤트 확인 플로우
def acknowledge_event(event_id: int, actor_user_id: int, note: str = ""):
    """관리자가 이벤트를 확인(ACKNOWLEDGED) 처리한다."""
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


def auto_resolve_active_events(
    *,
    event_type_prefix: str,
    sensor_id: int | None = None,
    power_device_id: int | None = None,
    cleared_gases: list[str] | None = None,
    note: str = "자동 정상화 (시나리오 NORMAL 복귀)",
) -> int:
    """정상 복귀 시 관련 ACTIVE Event 일괄 RESOLVED 처리.

    Why: fire_clear_*_task 가 토스트만 발송하던 결함 — 시나리오 RAMP_DOWN 후
    Event 가 ACTIVE 잔존해 시연 반복 시 누적. EventLog 로 audit trail 유지.

    sensor_id/power_device_id 둘 중 정확히 하나만 지정.

    cleared_gases (가스 케이스 한정): event 의 알람 gas_type 이 모두 이 set 안일
    때만 RESOLVED. 일부만 cleared 면 event 유지 — 다중 가스 시나리오에서 한
    가스만 normal 떨어져도 전체 event 가 RESOLVED 되어 격상 분기가 새 event_id
    로 빠지는 race 차단. None 이면 기존 sensor 단위 일괄 동작 (전력 호출 호환).

    Returns RESOLVED 처리된 Event 수.
    """
    import logging

    logger = logging.getLogger(__name__)

    qs = Event.objects.filter(
        event_type__startswith=event_type_prefix,
        status=EventStatus.ACTIVE,
    )
    if sensor_id:
        qs = qs.filter(source_sensor_id=sensor_id)
    elif power_device_id:
        qs = qs.filter(source_power_device_id=power_device_id)
    else:
        return 0

    # 가스 매칭 시 알람 prefetch — event 별 alarms.all() 의 N+1 회피.
    if cleared_gases is not None:
        qs = qs.prefetch_related("alarms")

    events = list(qs)
    if not events:
        return 0

    # 가스 케이스 — event 의 알람 gas_type 이 모두 cleared_gases 안일 때만 RESOLVED.
    if cleared_gases is not None:
        cleared_set = set(cleared_gases)
        filtered: list[Event] = []
        for event in events:
            event_gases = {a.gas_type for a in event.alarms.all() if a.gas_type}
            if not event_gases:
                # 운영 0건 확인됨 — 비정상 데이터 추적용 DEBUG 로그.
                logger.debug(
                    "auto_resolve skip — event=%s alarms 의 gas_type 모두 비어있음",
                    event.id,
                )
                continue
            if event_gases <= cleared_set:
                filtered.append(event)
            else:
                # partial clear — 다중 가스 중 일부만 normal. 디버깅 비용 절감.
                logger.info(
                    "auto_resolve skip — event=%s partial clear "
                    "(event_gases=%s, cleared=%s)",
                    event.id,
                    sorted(event_gases),
                    sorted(cleared_set),
                )
        events = filtered

    if not events:
        return 0

    now = timezone.now()
    for event in events:
        previous = event.status
        event.status = EventStatus.RESOLVED
        event.resolved_at = now
        event.save(update_fields=["status", "resolved_at"])
        EventLog.objects.create(
            event=event,
            action=EventLog.Action.RESOLVED,
            previous_status=previous,
            new_status=EventStatus.RESOLVED,
            note=note,
        )
    return len(events)
