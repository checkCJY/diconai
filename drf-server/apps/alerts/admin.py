from django.contrib import admin

from apps.alerts.models import AlarmRecord, Event, EventLog


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "summary",
        "facility",
        "event_type",
        "risk_level",
        "status",
        "first_detected_at",
    )
    list_filter = ("status", "risk_level", "event_type", "facility")
    search_fields = ("summary", "source_label")
    readonly_fields = ("created_at",)
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
