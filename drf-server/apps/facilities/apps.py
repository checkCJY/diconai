from django.apps import AppConfig


class FacilitiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.facilities"

    def ready(self):
        # Threshold 변경 시 Redis 캐시 invalidate (Phase 4-d)
        from apps.facilities import signals  # noqa: F401
