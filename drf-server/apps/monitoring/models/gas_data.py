# monitoring/models/gas_data.py

from django.db import models

from apps.core.constants import RiskLevel


class GasData(models.Model):
    """
    유해가스 센서 측정값 — wide table(고정 컬럼형) 구조

    [설계 원칙]
    - 가스 9종을 개별 FloatField 컬럼으로 저장합니다.
      이유: 시계열 집계(AVG, MAX), 임계치 비교, 대시보드 차트, AI 학습 파이프라인 모두
           컬럼 기반 구조에서 인덱스·ORM을 자연스럽게 활용할 수 있습니다.
    - 센서가 특정 가스를 미측정 또는 결측한 경우 → null=True, GasDataError에 기록
    - 0은 유효한 측정값(O2 등)이므로 결측 판별은 반드시 None으로 합니다.
    - raw_payload는 디버깅·원본 보관 전용이며 조회·집계에 사용하지 않습니다.

    [가스 종류 출처]
    센서별 데이터 구조 및 임계치 정의서 (디코나이 260401)
    """

    gas_sensor = models.ForeignKey(
        "facilities.GasSensor",
        on_delete=models.PROTECT,  # 센서 삭제 차단 (측정 이력 보존)
        related_name="gas_data",
    )

    # =====================================================================
    # 가스별 측정값 — 9종 개별 컬럼 (단위: ppm, o2는 %)
    # null=True: 해당 가스 미측정 또는 결측 (GasDataError에 사유 기록)
    # =====================================================================
    co = models.FloatField(null=True, verbose_name="일산화탄소 (ppm)")
    h2s = models.FloatField(null=True, verbose_name="황화수소 (ppm)")
    co2 = models.FloatField(null=True, verbose_name="이산화탄소 (ppm)")
    o2 = models.FloatField(null=True, verbose_name="산소 (%)")
    no2 = models.FloatField(null=True, verbose_name="이산화질소 (ppm)")
    so2 = models.FloatField(null=True, verbose_name="이산화황 (ppm)")
    o3 = models.FloatField(null=True, verbose_name="오존 (ppm)")
    nh3 = models.FloatField(null=True, verbose_name="암모니아 (ppm)")
    voc = models.FloatField(null=True, verbose_name="휘발성유기화합물 (ppm)")

    # =====================================================================
    # 가스별 위험도 — 9종 개별 컬럼
    # null=True: 해당 가스 결측 시 위험도 판정 불가
    # =====================================================================
    co_risk = models.CharField(
        max_length=10, choices=RiskLevel.choices, null=True, verbose_name="CO 위험도"
    )
    h2s_risk = models.CharField(
        max_length=10, choices=RiskLevel.choices, null=True, verbose_name="H2S 위험도"
    )
    co2_risk = models.CharField(
        max_length=10, choices=RiskLevel.choices, null=True, verbose_name="CO2 위험도"
    )
    o2_risk = models.CharField(
        max_length=10, choices=RiskLevel.choices, null=True, verbose_name="O2 위험도"
    )
    no2_risk = models.CharField(
        max_length=10, choices=RiskLevel.choices, null=True, verbose_name="NO2 위험도"
    )
    so2_risk = models.CharField(
        max_length=10, choices=RiskLevel.choices, null=True, verbose_name="SO2 위험도"
    )
    o3_risk = models.CharField(
        max_length=10, choices=RiskLevel.choices, null=True, verbose_name="O3 위험도"
    )
    nh3_risk = models.CharField(
        max_length=10, choices=RiskLevel.choices, null=True, verbose_name="NH3 위험도"
    )
    voc_risk = models.CharField(
        max_length=10, choices=RiskLevel.choices, null=True, verbose_name="VOC 위험도"
    )

    # 대시보드 빠른 필터링용 — 전체 가스 중 가장 높은 위험도 캐싱
    # save() 호출 시 자동 갱신됩니다 (아래 메서드 참고)
    max_risk_level = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.NORMAL,
        verbose_name="최고 위험도",
    )

    # 원본 페이로드 — 디버깅·감사 로그 전용, 조회·집계에는 사용하지 않습니다
    raw_payload = models.JSONField(
        null=True,
        blank=True,
        verbose_name="원본 수신 페이로드",
    )

    measured_at = models.DateTimeField(verbose_name="측정 시각")
    received_at = models.DateTimeField(auto_now_add=True, verbose_name="수신 시각")

    # RiskLevel 우선순위 (높을수록 위험)
    _RISK_ORDER = {
        RiskLevel.NORMAL: 0,
        RiskLevel.WARNING: 1,
        RiskLevel.DANGER: 2,
    }

    # 가스명 → risk 필드명 매핑 (내부 반복 처리용)
    _GAS_RISK_FIELDS = [
        "co_risk",
        "h2s_risk",
        "co2_risk",
        "o2_risk",
        "no2_risk",
        "so2_risk",
        "o3_risk",
        "nh3_risk",
        "voc_risk",
    ]

    def calculate_max_risk(self) -> str:
        """9종 가스 위험도 중 가장 높은 값을 반환한다. 모든 가스가 결측이면 NORMAL."""
        valid_risks = [
            getattr(self, field)
            for field in self._GAS_RISK_FIELDS
            if getattr(self, field) is not None
        ]
        if not valid_risks:
            return RiskLevel.NORMAL
        return max(valid_risks, key=lambda r: self._RISK_ORDER.get(r, 0))

    def save(self, *args, **kwargs):
        self.max_risk_level = self.calculate_max_risk()
        super().save(*args, **kwargs)

    @property
    def communication_delay_seconds(self) -> float:
        """통신 지연 시간(초) — measured_at과 received_at 차이"""
        return (self.received_at - self.measured_at).total_seconds()

    class Meta:
        db_table = "gas_data"
        indexes = [
            models.Index(
                fields=["gas_sensor", "-measured_at"],
                name="idx_gas_data_sensor_time",
            ),
            models.Index(
                fields=["-measured_at"],
                name="idx_gas_data_time",
            ),
            models.Index(
                fields=["max_risk_level", "-measured_at"],
                name="idx_gas_data_risk_time",
            ),
        ]


class GasDataError(models.Model):
    """
    가스 측정 에러·결측 기록 테이블

    [설계 원칙]
    - 1개 GasData row에서 여러 가스가 동시에 결측될 수 있으므로 별도 테이블로 분리합니다.
    - target_gas는 TextChoices로 제한하여 집계 쿼리 신뢰성을 보장합니다.
    """

    class GasType(models.TextChoices):
        """센서 정의서(디코나이 260401) 기준 가스 9종"""

        CO = "co", "일산화탄소"
        H2S = "h2s", "황화수소"
        CO2 = "co2", "이산화탄소"
        O2 = "o2", "산소"
        NO2 = "no2", "이산화질소"
        SO2 = "so2", "이산화황"
        O3 = "o3", "오존"
        NH3 = "nh3", "암모니아"
        VOC = "voc", "휘발성유기화합물"

    class ErrorType(models.TextChoices):
        MISSING = "MISSING", "데이터 누락(결측)"
        SENSOR_FAULT = "SENSOR_FAULT", "센서 고장"
        # TODO(팀): 캘리브레이션 필요 등 에러 코드 확장 가능

    gas_data = models.ForeignKey(
        GasData,
        on_delete=models.CASCADE,  # 원본 데이터 삭제 시 에러 기록도 함께 삭제
        related_name="errors",
    )

    target_gas = models.CharField(
        max_length=20,
        choices=GasType.choices,
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
                fields=["target_gas", "error_type"],
                name="idx_gas_error_target_type",
            ),
        ]
