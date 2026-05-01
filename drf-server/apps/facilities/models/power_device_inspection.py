from django.db import models


class PowerDeviceInspection(models.Model):
    class InspectionType(models.TextChoices):
        REGULAR = "regular", "정기"
        ABNORMAL = "abnormal", "이상"

    class InspectionStatus(models.TextChoices):
        ACTION_NEEDED = "action_needed", "조치 필요"
        NORMAL = "normal", "정상"

    device = models.ForeignKey(
        "facilities.PowerDevice",
        on_delete=models.CASCADE,
        related_name="inspections",
        verbose_name="전력 장치",
    )
    inspection_type = models.CharField(
        max_length=20,
        choices=InspectionType.choices,
        default=InspectionType.REGULAR,
        verbose_name="점검 유형",
    )
    inspection_date = models.DateField(verbose_name="점검일")
    inspector = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="power_inspections",
        verbose_name="점검자",
    )
    status = models.CharField(
        max_length=20,
        choices=InspectionStatus.choices,
        default=InspectionStatus.NORMAL,
        verbose_name="점검 결과",
    )
    notes = models.TextField(blank=True, default="", verbose_name="점검 내용")
    expected_action_date = models.DateField(
        null=True, blank=True, verbose_name="조치 예정일"
    )
    is_actioned = models.BooleanField(default=False, verbose_name="조치 완료")
    action_date = models.DateField(null=True, blank=True, verbose_name="조치 완료일")
    action_user = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="power_action_inspections",
        verbose_name="조치자",
    )
    action_notes = models.TextField(blank=True, default="", verbose_name="조치 내용")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "power_device_inspection"
        ordering = ["-inspection_date", "-created_at"]
        verbose_name = "전력 장치 점검"
