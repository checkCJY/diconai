from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "target_user",
        "is_broadcast",
        "severity",
        "channel",
        "delivery_status",
        "retry_count",
        "is_read",
        "created_at",
    )
    list_filter = ("delivery_status", "severity", "channel", "is_broadcast", "is_read")
    search_fields = ("title", "message", "target_user__username")
    readonly_fields = ("created_at", "last_attempted_at")
    ordering = ("-created_at",)
