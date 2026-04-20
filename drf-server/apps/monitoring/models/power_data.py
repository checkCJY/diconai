# monitoring/models/power_data.py
from django.db import models
from apps.core.constants import RiskLevel


class PowerData(models.Model):
    """
    전력 측정값 — 채널별 행으로 정규화 저장

    [구조 선택 근거]
    1장비 × 16채널 × 3종(전류/전압/전력) = 주기마다 48행
    48개 컬럼으로 가로 확장하면 채널 수 변경 대응 불가
    → 채널별 행(long-format)으로 정규화

    [복합 UNIQUE]
    (power_device, channel, data_type, measured_at)
    동일 시각 중복 저장 방지
    """

    class DataType(models.TextChoices):
        CURRENT = "current", "전류 (A)"
        VOLTAGE = "voltage", "전압 (V)"
        WATT = "watt", "전력 (W)"

    power_device = models.ForeignKey(
        "facilities.PowerDevice", on_delete=models.PROTECT, related_name="power_data"
    )
    channel = models.PositiveSmallIntegerField(verbose_name="채널 번호 (1~16)")
    data_type = models.CharField(
        max_length=20, choices=DataType.choices, verbose_name="측정 종류"
    )
    value = models.FloatField(verbose_name="측정값")
    risk_level = models.CharField(
        max_length=10, choices=RiskLevel.choices, default=RiskLevel.NORMAL
    )
    measured_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "power_data"
        constraints = [
            models.UniqueConstraint(
                fields=["power_device", "channel", "data_type", "measured_at"],
                name="uq_power_data_device_channel_type_time",
            )
        ]
        indexes = [
            models.Index(
                fields=["power_device", "channel", "-measured_at"],
                name="idx_pwr_device_ch_time",
            ),
            models.Index(fields=["-measured_at"], name="idx_pwr_time"),
            models.Index(
                fields=["risk_level", "-measured_at"], name="idx_pwr_risk_time"
            ),
        ]
