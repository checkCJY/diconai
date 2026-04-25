from django.contrib import admin

from apps.geofence.models import GeoFence


@admin.register(GeoFence)
class GeoFenceAdmin(admin.ModelAdmin):
    list_display = ("name", "facility", "risk_level", "is_active", "created_at")
    list_filter = ("risk_level", "is_active", "facility")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")
