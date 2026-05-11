from django.contrib import admin

from apps.dashboard.models import Menu, RoleMenuVisibility


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "menu_type",
        "parent",
        "sort_order",
        "url_path",
        "is_active",
    )
    list_filter = ("menu_type", "is_active")
    search_fields = ("code", "name", "url_path")
    list_select_related = ("parent",)


@admin.register(RoleMenuVisibility)
class RoleMenuVisibilityAdmin(admin.ModelAdmin):
    list_display = ("role_profile", "menu", "is_visible")
    list_filter = ("is_visible", "role_profile")
    list_select_related = ("role_profile", "menu")
