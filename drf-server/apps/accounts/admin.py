from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import (
    Company,
    CustomUser,
    Department,
    LoginLog,
    Position,
    RoleProfile,
    UserDepartment,
)


@admin.register(RoleProfile)
class RoleProfileAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "base_user_type", "platform_type", "is_active")
    list_filter = ("base_user_type", "platform_type", "is_active")
    search_fields = ("code", "name", "description")


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "user_type",
        "facility",
        "is_active",
        "date_joined",
    )
    list_filter = ("user_type", "is_active", "facility")
    search_fields = ("username", "email", "phone")
    ordering = ("-date_joined",)
    fieldsets = UserAdmin.fieldsets + (
        (
            "추가 정보",
            {
                "fields": (
                    "name",
                    "user_type",
                    "position",
                    "facility",
                    "phone",
                    "discord_id",
                    "failed_login_count",
                    "account_locked_until",
                    "deactivated_at",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "추가 정보",
            {
                "fields": (
                    "name",
                    "email",
                    "user_type",
                    "position",
                    "facility",
                    "phone",
                )
            },
        ),
    )


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    ordering = ("name",)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "company", "leader", "is_active")
    ordering = ("code",)


@admin.register(UserDepartment)
class UserDepartmentAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "is_primary", "joined_at")
    list_filter = ("is_primary",)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "category", "is_active")
    ordering = ("level",)


@admin.register(LoginLog)
class LoginLogAdmin(admin.ModelAdmin):
    list_display = ("user", "login_result", "is_login", "ip_address", "timestamp")
    list_filter = ("login_result", "is_login")
    search_fields = ("user__username", "ip_address")
    readonly_fields = (
        "user",
        "is_login",
        "login_result",
        "ip_address",
        "user_agent",
        "session_key",
        "timestamp",
    )
    ordering = ("-timestamp",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
