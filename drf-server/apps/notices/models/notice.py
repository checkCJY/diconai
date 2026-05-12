from django.conf import settings
from django.db import models

from apps.core.models.base import BaseModel


class Notice(BaseModel):
    """
    공지사항 — 시설/전사 단위로 발행되는 알림 외 게시물

    [Notification 재활용 불가]
    Notification은 event FK CASCADE + 발송 큐 인덱스에 최적화. 게시물 성격의
    공지사항(긴 본문, 첨부파일, 고정 노출)을 담기 부적합 → 별도 모델.

    [target_facility=NULL]
    NULL이면 전사 공지. 특정 facility 지정 시 해당 공장만 노출.

    [SET_NULL author]
    CustomUser는 Soft Delete 정책. 작성자 탈퇴 후에도 공지 보존 → SET_NULL.

    [is_pinned 정렬]
    화면 정렬 기본: -is_pinned, -published_at.
    """

    class Category(models.TextChoices):
        GENERAL = "general", "일반 공지"
        URGENT = "urgent", "긴급 공지"
        MAINTENANCE = "maintenance", "점검 안내"

    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.GENERAL
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notices_authored",
    )
    is_pinned = models.BooleanField(default=False, verbose_name="상단 고정")
    target_facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notices",
        help_text="NULL이면 전사 공지",
    )
    is_active = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)

    # ── 소프트 삭제 ──────────────────────────────────────────────────────────
    # 관리자가 공지를 삭제했을 때 누가/언제/무엇을 삭제했는지 추적 가능.
    # 실수 삭제 시 복구 가능. SET_NULL로 삭제자 탈퇴 후에도 이력 보존.
    is_deleted = models.BooleanField(default=False, verbose_name="삭제 여부")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="삭제 일시")
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notices_deleted",
        verbose_name="삭제자",
    )

    def __str__(self):
        return self.title

    class Meta:
        db_table = "notice"
        indexes = [
            models.Index(
                fields=["-is_pinned", "-published_at"],
                name="idx_notice_pinned_published",
            ),
            models.Index(
                fields=["category", "-published_at"], name="idx_notice_cat_published"
            ),
        ]
