from django.db import models

from apps.core.models.base import BaseModel


class HazardTypeGroup(BaseModel):
    """
    위험 유형 그룹 — HazardType 분류 (예: 환경 위험 / 설비 위험 / 작업자 위험)

    [용도]
    UI 관리 화면에서 위험 유형을 그룹별로 노출. 정책 화면에서도 그룹 기반 필터.
    """

    code = models.CharField(max_length=50, unique=True, verbose_name="그룹 코드")
    name = models.CharField(max_length=100, verbose_name="그룹 명")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.name})"

    class Meta:
        db_table = "hazard_type_group"
        ordering = ["sort_order", "code"]
