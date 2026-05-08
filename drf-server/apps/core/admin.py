from django.contrib import admin

from apps.core.models import RiskLevelStandard, SystemLog


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = (
        "action_type",
        "actor",
        "target_model",
        "target_id",
        "target_menu",
        "result",
        "ip_address",
        "created_at",
    )
    list_filter = ("action_type", "result")
    search_fields = (
        "actor__username",
        "target_model",
        "target_id",
        "target_menu",
        "target_name",
        "description",
    )
    readonly_fields = (
        "actor",
        "action_type",
        "target_model",
        "target_id",
        "target_menu",
        "target_name",
        "result",
        "old_value",
        "new_value",
        "description",
        "ip_address",
        "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RiskLevelStandard)
class RiskLevelStandardAdmin(admin.ModelAdmin):
    """
    RiskLevel 이넘과 1:1 강제 매핑 — code 필드는 readonly.
    운영자는 name/display_color/event_priority/alert_intensity만 수정 가능.
    """

    list_display = (
        "code",
        "name",
        "display_color",
        "alert_intensity",
        "event_priority",
        "is_active",
        "updated_at",
    )
    list_filter = ("alert_intensity", "is_active")
    readonly_fields = ("code", "created_at", "updated_at", "updated_by")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "code",
                    "name",
                    "display_color",
                    "alert_intensity",
                    "event_priority",
                    "is_active",
                    "description",
                ),
            },
        ),
        (
            "메타",
            {
                "fields": ("created_at", "updated_at", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )
