from django.contrib import admin

from apps.notices.models import Notice, NoticeAttachment


class NoticeAttachmentInline(admin.TabularInline):
    model = NoticeAttachment
    extra = 0
    fields = ("filename", "file", "size")
    readonly_fields = ("size",)


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "author",
        "is_pinned",
        "target_facility",
        "is_active",
        "published_at",
    )
    list_filter = ("category", "is_pinned", "is_active", "target_facility")
    search_fields = ("title", "content")
    raw_id_fields = ("author", "target_facility")
    inlines = [NoticeAttachmentInline]


@admin.register(NoticeAttachment)
class NoticeAttachmentAdmin(admin.ModelAdmin):
    list_display = ("notice", "filename", "size", "created_at")
    search_fields = ("filename",)
    raw_id_fields = ("notice",)
