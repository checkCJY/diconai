# notifications/services/notification_service.py

from django.db import transaction
from apps.notifications.models import Notification
from apps.accounts.models import CustomUser
from apps.core.constants import RiskLevel
from apps.notifications.services.template_renderer import render_alert_message


@transaction.atomic
def notify_event_created(event):
    """
    Event 생성 직후 호출되는 알림 발송 진입점
    - 해당 공장 관리자 전원에게 발송
    - severity에 따라 채널 결정

    [Phase 4-ef]
    - Event.policy(policy_matcher 매칭 결과)를 Notification.policy FK로 그대로 전달
    - policy.message_template이 비어있지 않으면 Django Template으로 메시지 렌더,
      그 외에는 Event.summary fallback (render_alert_message가 처리)
    """
    # 1. 심각도별 채널 결정
    channels = resolve_channels(event.risk_level)

    # 2. 수신자 결정 — 공장 관리자 전원
    recipients = CustomUser.objects.filter(
        facility=event.facility,
        user_type__in=["super_admin", "facility_admin"],
        is_active=True,
    )

    # Phase 4-f: AlertPolicy 템플릿 기반 메시지 렌더 (없으면 summary fallback)
    policy = event.policy
    template = policy.message_template if policy else ""
    context = {
        "source_label": event.source_label,
        "risk_level": event.risk_level,
        "level": event.risk_level,
        "summary": event.summary,
        "facility_name": event.facility.name if event.facility_id else "",
        "event_type": event.event_type,
    }
    rendered_message = render_alert_message(
        template=template, context=context, fallback=event.summary
    )

    # 3. 채널 × 수신자 조합으로 Notification 생성
    notifications = []
    for user in recipients:
        for channel in channels:
            notifications.append(
                Notification(
                    event=event,
                    policy=policy,
                    target_user=user,
                    is_broadcast=False,
                    severity=event.risk_level,
                    channel=channel,
                    title=f"[{event.get_risk_level_display()}] {event.source_label}",
                    message=rendered_message,
                )
            )
    Notification.objects.bulk_create(notifications)

    # 4. 발송 큐에 추가 (3차는 동기 발송, 4차는 Celery)
    for notif in notifications:
        dispatch_notification(notif)


def resolve_channels(risk_level: str) -> list[str]:
    """심각도별 발송 채널 결정"""
    if risk_level == RiskLevel.DANGER:
        return ["popup"]  # 4차에 'sms', 'push' 추가
    elif risk_level == RiskLevel.WARNING:
        return ["popup"]  # 4차에 'push' 추가
    return ["popup"]


def dispatch_notification(notif: Notification):
    """채널별 발송기 호출"""
    from apps.notifications.services.delivery import popup_delivery

    try:
        if notif.channel == Notification.Channel.POPUP:
            popup_delivery.send(notif)
        # 4차: sms, push, email 분기 추가
        else:
            raise NotImplementedError(f"Channel {notif.channel} not implemented")

        notif.delivery_status = Notification.DeliveryStatus.SENT
        from django.utils import timezone

        notif.sent_at = timezone.now()
        notif.save(update_fields=["delivery_status", "sent_at"])

    except Exception as e:
        notif.delivery_status = Notification.DeliveryStatus.FAILED
        notif.delivery_error = str(e)[:300]
        notif.save(update_fields=["delivery_status", "delivery_error"])
