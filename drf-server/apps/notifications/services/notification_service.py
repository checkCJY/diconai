# notifications/services/notification_service.py

from django.db import transaction
from apps.notifications.models import Notification
from apps.accounts.models import CustomUser
from apps.core.constants import RiskLevel


@transaction.atomic
def notify_event_created(event):
    """
    Event 생성 직후 호출되는 알림 발송 진입점
    - 해당 공장 관리자 전원에게 발송
    - severity에 따라 채널 결정
    """
    # 1. 심각도별 채널 결정
    channels = resolve_channels(event.risk_level)

    # 2. 수신자 결정 — 공장 관리자 전원
    recipients = CustomUser.objects.filter(
        facility=event.facility,
        user_type__in=["super_admin", "facility_admin"],
        is_active=True,
    )

    # 3. 채널 × 수신자 조합으로 Notification 생성
    notifications = []
    for user in recipients:
        for channel in channels:
            notifications.append(
                Notification(
                    event=event,
                    target_user=user,
                    is_broadcast=False,
                    severity=event.risk_level,
                    channel=channel,
                    title=f"[{event.get_risk_level_display()}] {event.source_label}",
                    message=event.summary,
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
    from notifications.services.delivery import popup_delivery

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
