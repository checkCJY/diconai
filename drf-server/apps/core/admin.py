from django.contrib import admin

from apps.core.models import SystemLog


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = (
        "action_type",
        "actor",
        "target_model",
        "target_id",
        "ip_address",
        "created_at",
    )
    list_filter = ("action_type",)
    search_fields = ("actor__username", "target_model", "target_id", "description")
    readonly_fields = (
        "actor",
        "action_type",
        "target_model",
        "target_id",
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
