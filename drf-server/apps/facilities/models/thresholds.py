import re

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import BaseModel


def validate_measurement_item(value):
    """
    measurement_item 형식 강제 — lowercase + 숫자 + 언더스코어만.
    예: 'co', 'h2s', 'co2', 'power_w', 'voltage'
    """
    if not re.match(r"^[a-z][a-z0-9_]*$", value):
        raise ValidationError(
            "measurement_item은 소문자/숫자/언더스코어만 허용 ([a-z][a-z0-9_]*)"
        )


class ThresholdGroup(BaseModel):
    """
    임계치 그룹 마스터 — 정책별 임계치 묶음

    [예시]
    - gas_legal: 산업안전보건법 기준 가스 임계치
    - gas_facility_default: 공장 기본 가스 임계치 (legal보다 보수적)
    - power_default: 전력 기본 임계치
    """

    code = models.CharField(max_length=50, unique=True, verbose_name="그룹 코드")
    name = models.CharField(max_length=100, verbose_name="그룹 명")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.name})"

    class Meta:
        db_table = "threshold_group"
        ordering = ["code"]


class Threshold(BaseModel):
    """
    임계치 — ThresholdGroup 내 측정 항목별 위험 구간

    [Phase 2 시점 사용]
    Phase 2에서는 모델만 신설. Phase 4에서 power_alarm.py / gas_data risk
    계산 로직을 본 모델 조회 + 캐시 기반으로 전환.

    [warning vs danger]
    warning_min ≤ value ≤ warning_max → RiskLevel.WARNING
    danger_min ≤ value or value ≤ danger_max → RiskLevel.DANGER
    범위 밖이면 RiskLevel.NORMAL.
    """

    group = models.ForeignKey(
        "facilities.ThresholdGroup",
        on_delete=models.PROTECT,
        related_name="thresholds",
    )
    measurement_item = models.CharField(
        max_length=50,
        validators=[validate_measurement_item],
        verbose_name="측정 항목",
    )
    warning_min = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    warning_max = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    danger_min = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    danger_max = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    unit = models.CharField(max_length=10, default="ppm")
    chart_max = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="차트 Y축 최대값",
        help_text="프론트 차트 스케일링용. 운영자가 어드민에서 조정",
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.group.code}.{self.measurement_item}"

    class Meta:
        db_table = "threshold"
        constraints = [
            models.UniqueConstraint(
                fields=["group", "measurement_item"],
                name="uq_threshold_group_item",
            ),
        ]
        ordering = ["group", "measurement_item"]
