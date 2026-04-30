from django.conf import settings
from django.db import models


class UserDepartment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dept_memberships",
        verbose_name="사용자",
    )
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="부서",
    )
    is_primary = models.BooleanField(default=True, verbose_name="주 소속 여부")
    joined_at = models.DateTimeField(auto_now_add=True, verbose_name="소속 시작일")

    class Meta:
        db_table = "user_department"
        unique_together = ("user", "department")
        verbose_name = "사용자-부서 소속"

    def __str__(self):
        label = "주" if self.is_primary else "겸직"
        return f"{self.user} → {self.department} ({label})"
