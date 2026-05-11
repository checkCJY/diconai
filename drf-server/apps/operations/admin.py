from django.contrib import admin

from apps.operations.models import AppLog, DataRetentionPolicy, IntegrationLog


@admin.register(AppLog)
class AppLogAdmin(admin.ModelAdmin):
    list_display = ("log_category", "level", "service_module", "created_at")
    list_filter = ("log_category", "level")
    search_fields = ("service_module", "message")
    readonly_fields = (
        "log_category",
        "service_module",
        "level",
        "message",
        "extra",
        "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IntegrationLog)
class IntegrationLogAdmin(admin.ModelAdmin):
    list_display = (
        "integration_type",
        "target_system",
        "result",
        "created_at",
    )
    list_filter = ("integration_type", "result")
    search_fields = ("target_system", "description")
    readonly_fields = (
        "integration_type",
        "target_system",
        "result",
        "description",
        "extra",
        "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DataRetentionPolicy)
class DataRetentionPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "device_type",
        "data_category",
        "raw_retention_days",
        "history_retention_days",
        "delete_cycle",
        "is_active",
        "manager",
        "updated_at",
    )
    list_filter = ("device_type", "data_category", "delete_cycle", "is_active")
    search_fields = ("memo",)
    raw_id_fields = ("manager",)
    readonly_fields = ("created_at", "updated_at", "updated_by")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "device_type",
                    "data_category",
                    "raw_retention_days",
                    "history_retention_days",
                    "delete_cycle",
                    "is_active",
                    "memo",
                    "manager",
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
