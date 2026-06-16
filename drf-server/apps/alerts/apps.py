from django.apps import AppConfig


class AlertsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.alerts"

    def ready(self):
        # signals 모듈 import 시점에 @receiver 등록 — AlertPolicy 캐시 자동 invalidate.
        from apps.alerts import signals  # noqa: F401
