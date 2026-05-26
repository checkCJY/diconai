from apps.notifications.models import Notification


def send(notif: Notification) -> None:
    """팝업 채널 발송.

    Notification 레코드는 bulk_create로 이미 DB에 저장된 상태이므로
    프론트엔드가 미읽음 알림 API를 조회할 때 자동으로 노출된다.
    실제 WebSocket 팝업 발송은 Celery 태스크 → FastAPI /internal/alarms/push/ 경로가 담당하므로
    여기서는 별도 발송 없이 DB 저장 완료로 간주한다.
    """
    pass
