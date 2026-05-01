from django.conf import settings
from django.db import models
from apps.core.models.base import BaseModel


class Department(BaseModel):
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="departments",
        verbose_name="회사",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="상위 부서",
    )
    name = models.CharField(max_length=100, verbose_name="부서명")
    code = models.CharField(max_length=20, unique=True, verbose_name="부서 코드")
    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leading_departments",
        verbose_name="조직장",
    )
    is_active = models.BooleanField(default=True, verbose_name="사용 여부")

    class Meta:
        db_table = "department"
        ordering = ["code"]
        verbose_name = "부서"

    def __str__(self):
        return self.name
