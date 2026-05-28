# notifications/services/notification_service.py

from django.db import transaction
from apps.notifications.models import Notification
from apps.accounts.models import CustomUser
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
    # 1. 정책 채널 우선, 미연결 시 심각도 기본값
    channels = resolve_channels(event)

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


def resolve_channels(event) -> list[str]:
    """Event 의 발송 채널 결정.

    AlertPolicy.channels 가 설정돼 있으면 그대로 사용 (어드민 정책 화면에서
    선택한 채널이 그대로 발송 대상이 됨). 정책 미연결 또는 channels 가 비어
    있으면 risk_level 기반 기본값 (popup) 으로 graceful fallback.
    """
    policy = getattr(event, "policy", None)
    if policy and policy.channels:
        valid = {c.value for c in Notification.Channel}
        chosen = [c for c in policy.channels if c in valid]
        if chosen:
            return chosen
    return ["popup"]


def dispatch_notification(notif: Notification):
    """채널별 발송기 호출.

    현재 POPUP 만 실제 발송. push/sms/email 은 delivery 모듈은 있으나 시연
    scope 에서는 정책 연동 가시화 목적으로 Notification 레코드만 PENDING 상태로
    남김 (실제 외부 발송은 4차에 자격증명 + delivery 모듈 본구현 후 분기 추가).
    """
    from apps.notifications.services.delivery import popup_delivery

    try:
        if notif.channel == Notification.Channel.POPUP:
            popup_delivery.send(notif)
            notif.delivery_status = Notification.DeliveryStatus.SENT
            from django.utils import timezone

            notif.sent_at = timezone.now()
            notif.save(update_fields=["delivery_status", "sent_at"])
        # 4차: PUSH/SMS/EMAIL — delivery 모듈 본구현 후 분기 추가.
        # 현재는 PENDING 유지로 정책 연동(어떤 채널이 발송 의도였는지) 가시화.
    except Exception as e:
        notif.delivery_status = Notification.DeliveryStatus.FAILED
        notif.delivery_error = str(e)[:300]
        notif.save(update_fields=["delivery_status", "delivery_error"])
