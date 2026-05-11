from django.db import models
from django.utils import timezone

from apps.core.models.base import BaseModel


class SafetyCheckSection(BaseModel):
    """
    체크리스트 섹션 — SafetyCheckItem의 그룹화 마스터 (Phase 3-b)

    [공장별 운영]
    facility FK 필수 — 다른 도메인 모델(SafetyCheckItem, GasSensor 등)이 모두
    facility 단위 운영. 권한 격리(시설관리자가 본인 facility만) 일관.

    [PROTECT 삭제 정책]
    Item이 남아있으면 Section 삭제 차단. 운영자가 Item 정리 후 삭제 강제 →
    데이터 손실 방지 (CASCADE는 위험, SET_NULL은 고아 Item 발생).

    [order 정렬 두 레벨]
    화면 정렬: ORDER BY (section.order, item.order). 결정문 §3b-6.
    """

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="safety_check_sections",
    )
    name = models.CharField(max_length=100, verbose_name="섹션 이름")
    description = models.TextField(blank=True, default="", verbose_name="섹션 설명")
    order = models.PositiveIntegerField(default=0, verbose_name="섹션 순서")
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    def deactivate(self, updated_by=None):
        self.is_active = False
        self.deactivated_at = timezone.now()
        if updated_by is not None:
            self.updated_by = updated_by
        self.save(
            update_fields=[
                "is_active",
                "deactivated_at",
                "updated_at",
                "updated_by",
            ]
        )

    def __str__(self):
        return f"{self.facility_id}/{self.name}"

    class Meta:
        db_table = "safety_check_section"
        ordering = ["facility", "order"]
        indexes = [
            models.Index(
                fields=["facility", "is_active", "order"],
                name="idx_section_fac_active_order",
            ),
        ]
