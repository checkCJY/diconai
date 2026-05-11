"""Menu / RoleMenuVisibility 변경 시 Redis 캐시 자동 invalidate (Phase 4-a)."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.dashboard.menu import invalidate_menu_tree_cache
from apps.dashboard.models import Menu, RoleMenuVisibility


@receiver([post_save, post_delete], sender=Menu)
@receiver([post_save, post_delete], sender=RoleMenuVisibility)
def invalidate_menu_cache_on_change(sender, instance, **kwargs):
    """Menu 또는 RoleMenuVisibility 변경 시 모든 role 캐시 무효화."""
    invalidate_menu_tree_cache()
