from django.contrib import admin, messages
from django.utils.html import format_html

from apps.operations.models import AppLog, DataRetentionPolicy, IntegrationLog


@admin.register(AppLog)
class AppLogAdmin(admin.ModelAdmin):
    list_display = ("log_category", "level", "service_module", "created_at")
    list_filter = ("log_category", "level")
    search_fields = ("service_module", "message")
    readonly_fields = (
        "log_category",
        "service_module",
        "level",
        "message",
        "extra",
        "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IntegrationLog)
class IntegrationLogAdmin(admin.ModelAdmin):
    list_display = (
        "integration_type",
        "target_system",
        "result",
        "created_at",
    )
    list_filter = ("integration_type", "result")
    search_fields = ("target_system", "description")
    readonly_fields = (
        "integration_type",
        "target_system",
        "result",
        "description",
        "extra",
        "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DataRetentionPolicy)
class DataRetentionPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "device_type",
        "data_category",
        "raw_retention_days",
        "history_retention_days",
        "delete_cycle",
        "is_active",
        "manager",
        "updated_at",
    )
    list_filter = ("device_type", "data_category", "delete_cycle", "is_active")
    search_fields = ("memo",)
    raw_id_fields = ("manager",)
    # affected_rows_preview: 편집 화면에서 현재 정책 기준 삭제 예정 행 수를 실시간 표시.
    # 저장 전에 영향 범위를 확인할 수 있도록 맨 위 섹션에 배치.
    readonly_fields = ("affected_rows_preview", "created_at", "updated_at", "updated_by")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "affected_rows_preview",
                    "device_type",
                    "data_category",
                    "raw_retention_days",
                    "history_retention_days",
                    "delete_cycle",
                    "is_active",
                    "memo",
                    "manager",
                ),
            },
        ),
        (
            "메타",
            {
                "fields": ("created_at", "updated_at", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="삭제 예정 행 수 (지금 배치 실행 시)")
    def affected_rows_preview(self, obj):
        """
        현재 정책 기준으로 지금 배치를 실행하면 삭제될 행 수를 표시.

        편집 화면 상단에 노출해 관리자가 기간 변경 전 영향 범위를 파악할 수 있게 함.
        count만 확인 (dry_run=True) — DB 변경 없음.
        """
        if obj.pk is None:
            return "-"
        try:
            from apps.operations.tasks.data_retention_task import _delete_for_policy

            count = _delete_for_policy(obj, dry_run=True)
            if count == 0:
                return format_html(
                    '<span style="color:#4caf50;font-weight:bold;">0행 (삭제 대상 없음)</span>'
                )
            return format_html(
                '<span style="color:#ff6b35;font-weight:bold;">'
                "{:,}행 — 다음 배치 실행 시 삭제됩니다"
                "</span>",
                count,
            )
        except Exception:
            return "계산 불가"

    def save_model(self, request, obj, form, change):
        """
        저장 시 보관 기간이 줄었으면 경고 메시지 표시.

        기간 단축은 되돌릴 수 없는 대량 삭제를 유발할 수 있으므로,
        저장 완료 후 삭제 예정 행 수를 경고 배너로 노출.
        """
        if change:
            try:
                original = DataRetentionPolicy.objects.get(pk=obj.pk)
                raw_reduced = obj.raw_retention_days < original.raw_retention_days
            except DataRetentionPolicy.DoesNotExist:
                raw_reduced = False

            super().save_model(request, obj, form, change)

            if raw_reduced:
                from apps.operations.tasks.data_retention_task import _delete_for_policy

                count = _delete_for_policy(obj, dry_run=True)
                self.message_user(
                    request,
                    (
                        f"⚠ 원천 보관 기간이 {original.raw_retention_days}일 → "
                        f"{obj.raw_retention_days}일로 줄었습니다. "
                        f"다음 배치 실행 시 약 {count:,}행이 삭제됩니다. "
                        "이 작업은 되돌릴 수 없습니다."
                    ),
                    level=messages.WARNING,
                )
        else:
            super().save_model(request, obj, form, change)
