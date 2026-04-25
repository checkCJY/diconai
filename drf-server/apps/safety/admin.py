from django.contrib import admin

from apps.safety.models import SafetyCheckItem, SafetyStatus


@admin.register(SafetyCheckItem)
class SafetyCheckItemAdmin(admin.ModelAdmin):
    list_display = ("title", "facility", "order", "is_required", "is_active")
    list_filter = ("is_required", "is_active", "facility")
    search_fields = ("title", "description")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("facility", "order")


@admin.register(SafetyStatus)
class SafetyStatusAdmin(admin.ModelAdmin):
    list_display = ("worker", "check_item_title", "is_checked", "checked_at")
    list_filter = ("is_checked",)
    search_fields = ("worker__username", "check_item_title")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-checked_at",)
