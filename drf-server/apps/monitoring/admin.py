from django.contrib import admin

from apps.monitoring.models import GasData, GasDataError, PowerData, PowerEvent


@admin.register(GasData)
class GasDataAdmin(admin.ModelAdmin):
    list_display = ("gas_sensor", "max_risk_level", "measured_at", "received_at")
    list_filter = ("max_risk_level", "gas_sensor__facility")
    search_fields = ("gas_sensor__device_name", "gas_sensor__device_id")
    readonly_fields = ("received_at",)
    ordering = ("-measured_at",)


@admin.register(GasDataError)
class GasDataErrorAdmin(admin.ModelAdmin):
    list_display = ("gas_data", "target_gas", "error_type")
    list_filter = ("target_gas", "error_type")


@admin.register(PowerData)
class PowerDataAdmin(admin.ModelAdmin):
    list_display = (
        "power_device",
        "channel",
        "data_type",
        "value",
        "risk_level",
        "measured_at",
    )
    list_filter = ("data_type", "risk_level", "power_device__facility")
    search_fields = ("power_device__device_name", "power_device__device_id")
    readonly_fields = ("received_at",)
    ordering = ("-measured_at",)


@admin.register(PowerEvent)
class PowerEventAdmin(admin.ModelAdmin):
    list_display = ("power_device", "trigger", "created_at")
    list_filter = ("trigger", "power_device__facility")
    search_fields = ("power_device__device_name", "power_device__device_id")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
