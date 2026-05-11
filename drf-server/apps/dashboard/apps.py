from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard"

    def ready(self):
        # Menu/RoleMenuVisibility 변경 시 Redis 캐시 invalidate (Phase 4-a)
        from apps.dashboard import signals  # noqa: F401
