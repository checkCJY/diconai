from django.contrib import admin

from apps.alerts.models import (
    AlarmRecord,
    AlertPolicy,
    Event,
    EventLog,
    HazardType,
    HazardTypeGroup,
)


@admin.register(HazardTypeGroup)
class HazardTypeGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(HazardType)
class HazardTypeAdmin(admin.ModelAdmin):
    list_display = (
        "type_code",
        "name",
        "group",
        "display_color",
        "map_visible",
        "is_active",
    )
    list_filter = ("group", "map_visible", "is_active")
    search_fields = ("type_code", "name", "description")
    list_select_related = ("group",)
    # type_code는 AlarmType 이넘과 1:1 강제 — 기존 row 코드 변경 시 CI 테스트 fail
    readonly_fields = ("type_code",)


@admin.register(AlertPolicy)
class AlertPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "event_type",
        "policy_kind",
        "target_facility",
        "is_active",
        "updated_at",
    )
    list_filter = ("event_type", "policy_kind", "is_active")
    search_fields = ("name", "description", "condition_summary")
    list_select_related = ("target_facility",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "summary",
        "facility",
        "event_type",
        "risk_level",
        "status",
        "policy",
        "first_detected_at",
    )
    list_filter = ("status", "risk_level", "event_type", "facility", "policy")
    search_fields = ("summary", "source_label", "description", "status_note")
    readonly_fields = ("created_at",)
    list_select_related = ("facility", "policy")
    ordering = ("-created_at",)


@admin.register(AlarmRecord)
class AlarmRecordAdmin(admin.ModelAdmin):
    list_display = (
        "facility",
        "alarm_type",
        "risk_level",
        "gas_type",
        "measured_value",
        "threshold_value",
        "created_at",
    )
    list_filter = ("alarm_type", "risk_level", "facility")
    search_fields = ("facility__name",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "actor",
        "action",
        "previous_status",
        "new_status",
        "created_at",
    )
    list_filter = ("action",)
    search_fields = ("actor__username", "note")
    readonly_fields = (
        "event",
        "actor",
        "action",
        "previous_status",
        "new_status",
        "note",
        "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
