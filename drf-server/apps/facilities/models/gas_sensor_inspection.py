from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models.base import BaseModel


class GasSensorInspection(BaseModel):
    class InspectionType(models.TextChoices):
        REGULAR = "regular", "정기 점검"
        ABNORMAL = "abnormal", "이상 점검"

    class InspectionStatus(models.TextChoices):
        ACTION_NEEDED = "action_needed", "조치 필요"
        NORMAL = "normal", "정상"

    sensor = models.ForeignKey(
        "facilities.GasSensor",
        on_delete=models.CASCADE,
        related_name="inspections",
        verbose_name="대상 센서",
    )
    inspection_type = models.CharField(
        max_length=20, choices=InspectionType.choices, verbose_name="점검 구분"
    )
    inspection_date = models.DateField(
        default=timezone.localdate, verbose_name="점검일"
    )
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gas_inspections",
        verbose_name="점검자",
    )
    status = models.CharField(
        max_length=20, choices=InspectionStatus.choices, verbose_name="점검 상태"
    )
    notes = models.TextField(verbose_name="점검 의견")
    expected_action_date = models.DateField(
        null=True, blank=True, verbose_name="예상 조치일"
    )

    # 조치 정보
    is_actioned = models.BooleanField(default=False, verbose_name="조치 완료")
    action_date = models.DateField(null=True, blank=True, verbose_name="조치 완료일")
    action_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gas_actions",
        verbose_name="조치 담당자",
    )
    action_notes = models.TextField(blank=True, default="", verbose_name="조치 의견")
    # created_at / updated_at / updated_by 는 BaseModel 상속

    class Meta:
        db_table = "gas_sensor_inspection"
        ordering = ["-inspection_date", "-created_at"]
        indexes = [
            models.Index(
                fields=["sensor", "inspection_date"], name="idx_insp_sensor_date"
            ),
        ]

    def __str__(self):
        return f"{self.sensor} 점검 {self.inspection_date}"
