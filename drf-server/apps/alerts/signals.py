"""AlertPolicy 변경 시 policy_matcher 캐시 자동 invalidate.

PR #80 (admin-panel 알림 정책 관리) 후속 — 관리자가 권고 조치 등 정책 필드를
PATCH/POST 로 변경해도 policy_matcher 의 5분 TTL 캐시가 옛 값을 반환해 다음
알람에 즉시 반영 안 되던 결함을 자동 invalidate 로 해소.

참조 구현: `apps/facilities/signals.py` (Threshold 캐시 invalidate 와 동일 패턴).
admin_views.py 의 DELETE 명시 호출은 fallback 안전망으로 유지.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.alerts.models import AlertPolicy
from apps.alerts.services.policy_matcher import invalidate_policy_cache


@receiver([post_save, post_delete], sender=AlertPolicy)
def invalidate_policy_cache_on_change(sender, instance, **kwargs):
    """AlertPolicy save/delete 시 해당 event_type 캐시 무효화.

    Django admin·DRF view·shell·loaddata·시그널 등 어디서 모델이 변경돼도
    자동 발화. 단 `QuerySet.update()` / `bulk_update()` / raw SQL UPDATE 는
    post_save 발화 X — 운영 흐름에서는 사용 X (admin 은 serializer.save() 경로).
    """
    invalidate_policy_cache(instance.event_type)
