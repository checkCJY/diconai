from django.db import models
from django.db.models import Q

from apps.core.models.base import BaseModel


class VRTrainingContent(BaseModel):
    """
    VR 교육 콘텐츠 — 적용 대상별 단일 콘텐츠 정책

    [부분 UniqueConstraint — Phase 2 §0 결정]
    is_active=True일 때만 (target_type, target_facility) 1개 제한.
    교체 시 기존 row는 is_active=False로 보존하고 새 row 생성 → 이력 보존.
    교체 이력은 VRTrainingRevision으로 추적.

    [target_type 2종 시작 — CJY plan §2.4 권고]
    GAS_SENSOR / GENERAL. 화면 요구가 다중 대상으로 확장되면 choices 추가
    (마이그레이션 0회).

    [URLField]
    저장소 변경 유연성 (S3/CDN 변경 시 모델 변경 불필요).
    """

    class TargetType(models.TextChoices):
        GAS_SENSOR = "gas_sensor", "가스 센서"
        GENERAL = "general", "일반"

    target_type = models.CharField(
        max_length=20,
        choices=TargetType.choices,
        verbose_name="적용 대상",
    )
    target_facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="vr_contents",
        help_text="NULL이면 전사 콘텐츠",
    )
    name = models.CharField(max_length=200)
    content_url = models.URLField(max_length=500)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_target_type_display()})"

    class Meta:
        db_table = "vr_training_content"
        constraints = [
            # 부분 UniqueConstraint: is_active=True 인 row만 (target_type, target_facility) 1개
            models.UniqueConstraint(
                fields=["target_type", "target_facility"],
                condition=Q(is_active=True),
                name="uq_vr_active_target",
            ),
        ]
        indexes = [
            models.Index(
                fields=["target_type", "target_facility", "is_active"],
                name="idx_vr_target_active",
            ),
        ]
