from django.contrib import admin

from apps.training.models import VRTrainingContent, VRTrainingRevision


@admin.register(VRTrainingContent)
class VRTrainingContentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "target_type",
        "target_facility",
        "content_url",
        "is_active",
        "updated_at",
    )
    list_filter = ("target_type", "is_active", "target_facility")
    search_fields = ("name", "description", "content_url")
    raw_id_fields = ("target_facility",)


@admin.register(VRTrainingRevision)
class VRTrainingRevisionAdmin(admin.ModelAdmin):
    list_display = (
        "content",
        "previous_name",
        "replaced_by",
        "replaced_at",
    )
    list_filter = ("replaced_at",)
    search_fields = ("previous_name", "previous_url", "reason")
    readonly_fields = ("replaced_at",)
    raw_id_fields = ("content", "replaced_by")
