# monitoring/models/gas_data.py
from django.db import models
from apps.core.constants import RiskLevel


class GasData(models.Model):
    """
    가스 측정값 — JSONField를 활용한 유연한 스키마 구조

    [JSON 데이터 정책]
    가스 종류가 늘어나거나 줄어들어도 모델 변경(Migration)이 필요 없습니다.
    예시: {"co": {"value": 15.5, "risk": "WARNING"}, "o2": {"value": 0.0, "risk": "DANGER"}}
    결측값은 JSON에서 아예 키를 생략하고 GasDataError 테이블에 기록합니다.
    """

    gas_sensor = models.ForeignKey(
        "facilities.GasSensor",
        on_delete=models.PROTECT,  # 센서 삭제 차단 (측정 이력 보존)
        related_name="gas_data",
    )

    # 10개의 하드코딩된 필드 제거 -> 하나의 JSONField로 통합
    measurements = models.JSONField(
        default=dict, verbose_name="가스별 측정값 및 위험도"
    )

    # 전체 측정 상황 중 가장 높은 위험도를 캐싱 (대시보드 빠른 필터링 용도)
    max_risk_level = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.NORMAL,
        verbose_name="최고 위험도",
    )

    measured_at = models.DateTimeField(verbose_name="측정 시각")
    received_at = models.DateTimeField(auto_now_add=True, verbose_name="수신 시각")

    @property
    def communication_delay_seconds(self) -> float:
        """통신 지연 시간(초) — measured_at과 received_at 차이"""
        return (self.received_at - self.measured_at).total_seconds()

    class Meta:
        db_table = "gas_data"
        indexes = [
            models.Index(
                fields=["gas_sensor", "-measured_at"], name="idx_gas_data_sensor_time"
            ),
            models.Index(fields=["-measured_at"], name="idx_gas_data_time"),
            models.Index(
                fields=["max_risk_level", "-measured_at"], name="idx_gas_data_risk_time"
            ),
            # PostgreSQL 환경이라면 향후 특정 가스에 대한 GinIndex 추가도 가능합니다.
        ]


class GasDataError(models.Model):
    """
    에러/결측 기록 테이블 — 단일 문자열(error_field)의 한계 극복
    통계 및 다중 에러 동시 발생에 완벽하게 대응합니다.
    """

    class ErrorType(models.TextChoices):
        MISSING = "MISSING", "데이터 누락(결측)"
        SENSOR_FAULT = "SENSOR_FAULT", "센서 고장"
        # 향후 캘리브레이션 필요 등 에러 코드 확장 가능

    gas_data = models.ForeignKey(
        GasData,
        on_delete=models.CASCADE,  # 원본 데이터 삭제 시 에러 기록도 함께 삭제
        related_name="errors",
    )

    target_gas = models.CharField(
        max_length=20,
        help_text="오류가 발생한 가스 (예: 'co', 'o2', 'system')",
        verbose_name="대상 가스",
    )

    error_type = models.CharField(
        max_length=20,
        choices=ErrorType.choices,
        default=ErrorType.MISSING,
        verbose_name="에러 유형",
    )

    class Meta:
        db_table = "gas_data_error"
        indexes = [
            models.Index(
                fields=["target_gas", "error_type"], name="idx_gas_error_target_type"
            ),
        ]
