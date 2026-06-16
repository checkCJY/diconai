from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

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


@receiver(post_delete, sender=NoticeAttachment)
def delete_attachment_file(sender, instance, **kwargs):
    """
    NoticeAttachment DB행 삭제 시 MEDIA_ROOT 물리 파일도 함께 삭제.

    Notice가 CASCADE 삭제되면 연결된 NoticeAttachment가 순차적으로 삭제되고,
    각 행마다 이 시그널이 발화 → 파일 고아(orphan) 문제 방지.
    파일이 이미 없거나 삭제 실패 시 조용히 무시 (DB 롤백 트리거 안 함).
    """
    if instance.file:
        # save=False: FileField.delete()가 내부적으로 model.save()를 호출하는 것을 막음.
        # post_delete 시점에 instance.pk가 이미 None이므로 save() 호출 시 새 row 생성되는
        # Django 버그 회피.
        instance.file.delete(save=False)
