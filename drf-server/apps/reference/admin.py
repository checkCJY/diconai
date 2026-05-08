from django.contrib import admin

from apps.reference.models import CodeGroup, CommonCode


class CommonCodeInline(admin.TabularInline):
    model = CommonCode
    extra = 0
    fields = ("code", "name", "sort_order", "is_active")
    ordering = ("sort_order", "code")


@admin.register(CodeGroup)
class CodeGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")
    inlines = [CommonCodeInline]


@admin.register(CommonCode)
class CommonCodeAdmin(admin.ModelAdmin):
    list_display = ("group", "code", "name", "sort_order", "is_active", "updated_at")
    list_filter = ("group", "is_active")
    search_fields = ("code", "name", "description")
    list_select_related = ("group",)
