from django.contrib import admin

from apps.operations.models import DataRetentionPolicy


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
