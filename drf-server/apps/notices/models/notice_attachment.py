from django.db import models

from apps.core.models.base import BaseModel
from apps.notices.validators import validate_allowed_extension, validate_max_10mb


def notice_attachment_path(instance, filename):
    return f"notices/{instance.notice_id}/{filename}"


class NoticeAttachment(BaseModel):
    """
    공지사항 첨부파일 — 1 Notice : N Attachment

    [제약 — Phase 2 §0-4]
    최대 10MB, 허용 확장자: jpg/png/gif/pdf/docx/xlsx/pptx
    validators는 apps/notices/validators.py — 향후 다른 첨부 도메인 등장 시
    apps/core/validators.py로 이동 (Simplicity First, CJY plan §2.5).
    """

    notice = models.ForeignKey(
        "notices.Notice",
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        upload_to=notice_attachment_path,
        validators=[validate_max_10mb, validate_allowed_extension],
    )
    filename = models.CharField(max_length=200, verbose_name="원본 파일명")
    size = models.PositiveIntegerField(verbose_name="파일 크기(byte)")

    def __str__(self):
        return f"{self.notice.title} — {self.filename}"

    class Meta:
        db_table = "notice_attachment"
        indexes = [models.Index(fields=["notice"])]
