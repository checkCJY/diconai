"""Threshold 변경 시 Redis 캐시 자동 invalidate (Phase 4-d)."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.facilities.models import Threshold
from apps.facilities.services.threshold_service import invalidate_threshold_cache


@receiver([post_save, post_delete], sender=Threshold)
def invalidate_threshold_cache_on_change(sender, instance, **kwargs):
    """
    Threshold 모델 변경 시 해당 (group_code, measurement_item) 캐시 무효화.
    save/delete 양쪽 모두 처리.
    """
    invalidate_threshold_cache(instance.group.code, instance.measurement_item)
