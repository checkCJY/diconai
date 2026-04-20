# core/services/audit_service.py
from core.models import SystemLog


def log_action(
    actor_id: int,
    action_type: str,
    target_model: str = "",
    target_id: str = "",
    old_value: dict = None,
    new_value: dict = None,
    description: str = "",
    ip_address: str = None,
):
    """
    SystemLog 기록 헬퍼
    모든 관리자 행동의 감사 로그 기록은 이 함수를 통해 수행
    """
    SystemLog.objects.create(
        actor_id=actor_id,
        action_type=action_type,
        target_model=target_model,
        target_id=str(target_id) if target_id else "",
        old_value=old_value,
        new_value=new_value,
        description=description,
        ip_address=ip_address,
    )
