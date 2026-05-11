from django.db import models

from apps.core.models.base import BaseModel


class CommonCode(BaseModel):
    """
    공통 코드 — CodeGroup 내 개별 코드값

    UNIQUE(group, code)로 그룹 내 코드 중복 방지.
    sort_order로 화면 정렬 순서 제어.
    """

    group = models.ForeignKey(
        "reference.CodeGroup",
        on_delete=models.CASCADE,
        related_name="codes",
        verbose_name="소속 그룹",
    )
    code = models.CharField(max_length=50, verbose_name="코드")
    name = models.CharField(max_length=200, verbose_name="코드 명")
    description = models.TextField(blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.group.code}.{self.code}"

    class Meta:
        db_table = "ref_common_code"
        constraints = [
            models.UniqueConstraint(
                fields=["group", "code"], name="uq_commoncode_group_code"
            ),
        ]
        indexes = [
            models.Index(
                fields=["group", "sort_order"], name="idx_commoncode_group_order"
            ),
        ]
        ordering = ["group", "sort_order", "code"]
