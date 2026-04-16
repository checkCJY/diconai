from django.db import models


class Facility(models.Model):
    """
    공장 — 모든 모델의 최상위 단위
    멀티테넌트 구조의 핵심
    is_active로 폐업/운영중단 시 데이터 보존하며 비활성화
    """

    manager = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_facilities'
    )
    name       = models.CharField(max_length=200)
    address    = models.CharField(max_length=500)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'facility'


class GasSensor(models.Model):
    """
    가스 센서 장비 마스터 정보
    장비 위치(x, y)는 고정, 측정값만 주기적으로 변함
    last_reading으로 '5분 이상 미수신 = 통신 장애 의심' 판단 가능
    """

    class Status(models.TextChoices):
        NORMAL  = 'normal',  '정상'
        ERROR   = 'error',   '오류'
        OFFLINE = 'offline', '오프라인'

    facility     = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='gas_sensors'
    )
    device_id    = models.CharField(max_length=50, unique=True)
    device_name  = models.CharField(max_length=20)
    x            = models.FloatField()
    y            = models.FloatField()
    status       = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.NORMAL
    )
    last_reading = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device_name} ({self.device_id})"

    class Meta:
        db_table = 'gas_sensor'


class PowerDevice(models.Model):
    """
    전력 장비 마스터 정보
    16채널 스마트 파워 측정 장치 (에어위드 프로토콜)
    """

    class Status(models.TextChoices):
        NORMAL  = 'normal',  '정상'
        ERROR   = 'error',   '오류'
        OFFLINE = 'offline', '오프라인'

    facility      = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='power_devices'
    )
    device_id     = models.CharField(max_length=50, unique=True)
    device_name   = models.CharField(max_length=50)
    x             = models.FloatField()
    y             = models.FloatField()
    channel_count = models.IntegerField(default=16)
    status        = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.NORMAL
    )
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device_name} ({self.device_id})"

    class Meta:
        db_table = 'power_device'


class GasData(models.Model):
    """
    가스 측정값 — 1분 주기, 9종 가스를 한 행에 저장
    ⚠️ 가스 수치 전부 NULL 허용 — 0은 유효한 측정값, 결측 기본값으로 0 사용 금지
    measured_at(측정 시각) vs received_at(수신 시각) 차이로 통신 지연 감지
    """

    class RiskLevel(models.IntegerChoices):
        NORMAL  = 0, '정상'
        WARNING = 1, '주의'
        DANGER  = 2, '위험'

    gas_sensor   = models.ForeignKey(
        GasSensor,
        on_delete=models.CASCADE,
        related_name='gas_data'
    )
    # 9종 가스 수치 — 전부 NULL 허용
    co           = models.FloatField(null=True, blank=True)  # 일산화탄소 (ppm)
    h2s          = models.FloatField(null=True, blank=True)  # 황화수소 (ppm)
    co2          = models.FloatField(null=True, blank=True)  # 이산화탄소 (ppm)
    o2           = models.FloatField(null=True, blank=True)  # 산소 (%) — 낮을수록 위험
    no2          = models.FloatField(null=True, blank=True)  # 이산화질소 (ppm)
    so2          = models.FloatField(null=True, blank=True)  # 이산화황 (ppm)
    o3           = models.FloatField(null=True, blank=True)  # 오존 (ppm)
    nh3          = models.FloatField(null=True, blank=True)  # 암모니아 (ppm)
    voc          = models.FloatField(null=True, blank=True)  # 휘발성유기화합물 (ppm)
    lel          = models.FloatField(null=True, blank=True)  # 가연성 가스 폭발하한계 (%)

    risk_level   = models.IntegerField(
        choices=RiskLevel.choices,
        default=RiskLevel.NORMAL
    )
    error_field  = models.CharField(max_length=50, null=True, blank=True)
    measured_at  = models.DateTimeField()
    received_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.gas_sensor.device_id} - {self.measured_at}"

    class Meta:
        db_table = 'gas_data'
        ordering = ['-measured_at']
        indexes = [
            models.Index(
                fields=['gas_sensor', '-measured_at'],
                name='idx_gas_data_sensor_time'
            )
        ]


class PowerData(models.Model):
    """
    전력 측정값 — 16채널을 채널별 행으로 정규화 저장
    1장비 × 16채널 × 3종(전류/전압/전력) = 1분마다 48행 생성
    """

    class DataType(models.TextChoices):
        CURRENT = 'current', '전류 (A)'
        VOLTAGE = 'voltage', '전압 (V)'
        WATT    = 'watt',    '전력 (W)'

    class RiskLevel(models.IntegerChoices):
        NORMAL  = 0, '정상'
        WARNING = 1, '주의'
        DANGER  = 2, '위험'

    power_device = models.ForeignKey(
        PowerDevice,
        on_delete=models.CASCADE,
        related_name='power_data'
    )
    channel      = models.IntegerField()
    data_type    = models.CharField(max_length=30, choices=DataType.choices)
    value        = models.FloatField()
    risk_level   = models.IntegerField(
        choices=RiskLevel.choices,
        null=True,
        blank=True
    )
    measured_at  = models.DateTimeField()
    received_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.power_device.device_id} - ch{self.channel} {self.data_type}"

    class Meta:
        db_table = 'power_data'
        ordering = ['-measured_at']
        constraints = [
            models.UniqueConstraint(
                fields=['power_device', 'channel', 'measured_at'],
                name='uq_power_data_device_channel_time'
            )
        ]
        indexes = [
            models.Index(
                fields=['power_device', 'channel', '-measured_at'],
                name='idx_pwr_ch_time'
            )
        ]


class PowerEvent(models.Model):
    """
    전력 상태 스냅샷 — 16채널 전체 ON/OFF 상태를 JSON으로 원자성 보장
    PowerData(주기적 측정)와 역할 다름 — 이벤트성 ON/OFF 기록 전용
    """

    power_device = models.ForeignKey(
        PowerDevice,
        on_delete=models.CASCADE,
        related_name='power_events'
    )
    snapshot     = models.JSONField()
    created_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.power_device.device_id} - {self.created_at}"

    class Meta:
        db_table = 'power_event'
        ordering = ['-created_at']