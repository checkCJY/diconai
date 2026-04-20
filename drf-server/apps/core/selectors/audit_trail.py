# core/selectors/audit_trail.py
from core.models import SystemLog


def get_audit_trail(target_model: str, target_id: str | int):
    """
    특정 대상에 대한 모든 감사 로그 시계열 조회
    예: GasSensor id=5의 모든 변경 이력
    """
    return (
        SystemLog.objects.filter(
            target_model=target_model,
            target_id=str(target_id),
        )
        .select_related("actor")
        .order_by("-created_at")
    )


def get_actor_activity(actor_user_id: int, days: int = 30):
    """
    특정 관리자의 최근 활동 이력
    """
    from django.utils import timezone
    from datetime import timedelta

    since = timezone.now() - timedelta(days=days)

    return SystemLog.objects.filter(
        actor_id=actor_user_id,
        created_at__gte=since,
    ).order_by("-created_at")
