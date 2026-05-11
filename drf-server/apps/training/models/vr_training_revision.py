from django.conf import settings
from django.db import models

from apps.core.models.base import BaseModel


class VRTrainingRevision(BaseModel):
    """
    VR 교육 콘텐츠 교체 이력 — 산재 예방 시스템 감사 요건

    [기록 시점]
    VRTrainingContent를 교체할 때 이전 url/name을 스냅샷으로 보존.
    화면에서 "어떤 콘텐츠가 언제 누구에 의해 교체되었는가" 조회 가능.

    [SET_NULL replaced_by]
    CustomUser Soft Delete 정책 일관.
    """

    content = models.ForeignKey(
        "training.VRTrainingContent",
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    previous_url = models.URLField(max_length=500, verbose_name="이전 URL")
    previous_name = models.CharField(max_length=200, verbose_name="이전 명")
    replaced_at = models.DateTimeField(auto_now_add=True)
    replaced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vr_revisions_replaced",
    )
    reason = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.content_id} @ {self.replaced_at}"

    class Meta:
        db_table = "vr_training_revision"
        indexes = [
            models.Index(
                fields=["content", "-replaced_at"], name="idx_vrrev_content_time"
            ),
        ]
