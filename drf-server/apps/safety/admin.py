from django.contrib import admin

from apps.safety.models import SafetyCheckItem, SafetyCheckSection, SafetyStatus


@admin.register(SafetyCheckSection)
class SafetyCheckSectionAdmin(admin.ModelAdmin):
    list_display = ("name", "facility", "order", "is_active")
    list_filter = ("is_active", "facility")
    search_fields = ("name", "description")
    ordering = ("facility", "order")


@admin.register(SafetyCheckItem)
class SafetyCheckItemAdmin(admin.ModelAdmin):
    list_display = ("title", "facility", "section", "order", "is_required", "is_active")
    list_filter = ("is_required", "is_active", "facility", "section")
    search_fields = ("title", "description")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("facility", "section")
    ordering = ("facility", "section", "order")


@admin.register(SafetyStatus)
class SafetyStatusAdmin(admin.ModelAdmin):
    list_display = ("worker", "check_item_title", "is_checked", "checked_at")
    list_filter = ("is_checked",)
    search_fields = ("worker__username", "check_item_title")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-checked_at",)
