from django.contrib import admin

from apps.positioning.models import WorkerPosition


@admin.register(WorkerPosition)
class WorkerPositionAdmin(admin.ModelAdmin):
    list_display = (
        "worker",
        "facility",
        "x",
        "y",
        "movement_status",
        "current_geofence",
        "measured_at",
    )
    list_filter = ("movement_status", "facility")
    search_fields = ("worker__username",)
    readonly_fields = ("received_at",)
    ordering = ("-measured_at",)
