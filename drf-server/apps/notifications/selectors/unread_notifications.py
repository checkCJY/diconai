# notifications/selectors/unread_notifications.py

from apps.notifications.models import Notification


def get_unread_notifications_for_user(user, limit: int = 20):
    """
    사용자의 미읽음 알림 조회
    - 개인 알림: target_user=user
    - 브로드캐스트: 공장 전체 대상 (3차는 is_read 추적 불가)
    """
    return (
        Notification.objects.filter(
            target_user=user,
            is_read=False,
        )
        .select_related("event")
        .order_by("-created_at")[:limit]
    )
