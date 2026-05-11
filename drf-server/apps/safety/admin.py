from django.contrib import admin

from apps.safety.models import (
    SafetyCheckItem,
    SafetyCheckSection,
    SafetyCheckSession,
    SafetyChecklistRevision,
    SafetyStatus,
)


@admin.register(SafetyChecklistRevision)
class SafetyChecklistRevisionAdmin(admin.ModelAdmin):
    list_display = ("facility", "version", "is_active", "published_by", "published_at")
    list_filter = ("is_active", "facility")
    search_fields = ("facility__name",)
    readonly_fields = ("published_at", "revision_data")
    list_select_related = ("facility", "published_by")
    ordering = ("facility", "-version")


@admin.register(SafetyCheckSession)
class SafetyCheckSessionAdmin(admin.ModelAdmin):
    list_display = ("worker", "date", "revision", "is_completed", "completed_at")
    list_filter = ("is_completed", "date")
    search_fields = ("worker__username",)
    readonly_fields = ("completed_at",)
    list_select_related = ("worker", "revision")
    ordering = ("-date",)


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
    list_display = ("worker", "check_item_title", "session", "is_checked", "checked_at")
    list_filter = ("is_checked",)
    search_fields = ("worker__username", "check_item_title")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("worker", "check_item", "session")
    ordering = ("-checked_at",)
