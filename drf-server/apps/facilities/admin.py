from django.contrib import admin

from apps.facilities.models import Facility, GasSensor, PowerDevice


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "manager", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "address")
    readonly_fields = ("created_at", "updated_at")


@admin.register(GasSensor)
class GasSensorAdmin(admin.ModelAdmin):
    list_display = (
        "device_name",
        "device_id",
        "facility",
        "status",
        "is_active",
        "last_reading",
    )
    list_filter = ("status", "is_active", "facility")
    search_fields = ("device_name", "device_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PowerDevice)
class PowerDeviceAdmin(admin.ModelAdmin):
    list_display = (
        "device_name",
        "device_id",
        "facility",
        "channel_count",
        "status",
        "is_active",
    )
    list_filter = ("status", "is_active", "facility")
    search_fields = ("device_name", "device_id")
    readonly_fields = ("created_at", "updated_at")
