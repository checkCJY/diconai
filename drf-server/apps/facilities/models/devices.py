# facilities/models/devices.py
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from datetime import timedelta


class DeviceBase(models.Model):
    """
    현장 장비 공통 추상 모델 — GasSensor, PowerDevice가 상속

    [공통 필드]
    - facility: 소속 공장 (PROTECT)
    - device_id: 하드웨어 식별자 (전체 유일)
    - device_name: 사용자 정의 이름
    - x, y: 공장 도면 픽셀 좌표
    - status: 통신 상태
    - last_reading: 마지막 데이터 수신 시각
    - is_active: Soft Delete 플래그
    """

    class Status(models.TextChoices):
        NORMAL = "normal", "정상"
        ERROR = "error", "오류"
        OFFLINE = "offline", "오프라인"
        INACTIVE = "inactive", "비활성"

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,  # 공장 삭제 차단 (하위 센서 존재 시)
        related_name="%(class)ss",
    )
    device_id = models.CharField(
        max_length=50, unique=True, verbose_name="하드웨어 식별자"
    )
    device_name = models.CharField(
        max_length=100,  # v2의 20 → 100으로 확대
        verbose_name="사용자 정의 이름",
    )
    x = models.FloatField(verbose_name="도면 x 좌표 (px)")
    y = models.FloatField(verbose_name="도면 y 좌표 (px)")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NORMAL
    )
    status_updated_at = models.DateTimeField(null=True, blank=True)
    last_reading = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_communication_lost(self) -> bool:
        """5분 이상 데이터 미수신 여부"""
        if not self.last_reading:
            return True
        return (timezone.now() - self.last_reading) > timedelta(minutes=5)

    def deactivate(self):
        """장비 비활성화 (철거/교체 시)"""
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.status = self.Status.INACTIVE
        self.save(update_fields=["is_active", "deactivated_at", "status", "updated_at"])

    class Meta:
        abstract = True


class GasSensor(DeviceBase):
    """
    가스 센서 장비 마스터

    [좌표계]
    x, y는 facility의 공장 도면 픽셀 좌표 (좌상단 원점)
    GeoFence, WorkerPosition과 동일 좌표계
    도면 해상도 변경 시 일괄 환산 필요 (4차)

    [상태 관리]
    - NORMAL: 정상 수신 중
    - OFFLINE: last_reading 기준 5분 이상 미수신 (Celery Beat로 자동 판단)
    - ERROR: 센서 하드웨어 이상 신호 또는 관리자 수동 변경
    - INACTIVE: 철거/교체로 비활성화 (is_active=False와 함께)

    [교체 정책]
    교체 시 기존 레코드를 deactivate()하고 신규 레코드 생성
    과거 GasData는 구 센서 FK를 유지하여 이력 보존
    """

    def __str__(self):
        return f"{self.device_name} ({self.device_id})"

    class Meta:
        db_table = "gas_sensor"
        indexes = [
            models.Index(
                fields=["facility", "is_active"], name="idx_gas_sensor_facility_active"
            ),
            models.Index(fields=["status", "is_active"], name="idx_gas_sensor_status"),
        ]


class PositionNode(DeviceBase):
    """
    위치 추적 앵커 노드 (UWB/BLE 기반)

    작업자 위치 측정을 위해 공장 내 설치되는 고정 수신기.
    x, y는 도면 상 노드 설치 좌표.
    """

    def __str__(self):
        return f"{self.device_name} ({self.device_id})"

    class Meta:
        db_table = "position_node"
        indexes = [
            models.Index(
                fields=["facility", "is_active"], name="idx_pos_node_facility_active"
            ),
        ]


class PowerDevice(DeviceBase):
    """
    전력 장비 마스터

    16채널 스마트 파워 측정 장치 (에어위드 프로토콜)
    [채널 메타데이터]
    JSONField를 활용하여 채널별 용도(이름), 배율(Scale), 오프셋 등을 단일 테이블에서 통합 관리.
    """

    channel_count = models.PositiveSmallIntegerField(default=16, verbose_name="채널 수")

    # 모델 분리 대신 JSONField 도입
    channel_meta = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="채널 메타데이터",
        help_text='예: {"1": {"name": "메인 에어컨", "scale": 1.5, "offset": 0}, "2": {"name": "조명", "scale": 1.0, "offset": -0.5}}',
    )

    def __str__(self):
        return f"{self.device_name} ({self.device_id})"

    def clean(self):
        for ch_key, meta in self.channel_meta.items():
            if not ch_key.isdigit() or not (1 <= int(ch_key) <= self.channel_count):
                raise ValidationError(f"잘못된 채널 키: {ch_key}")
            if "name" not in meta:
                raise ValidationError(f"채널 {ch_key}에 'name' 필드가 없습니다.")

    class Meta:
        db_table = "power_device"
        indexes = [
            models.Index(
                fields=["facility", "is_active"],
                name="idx_pwrdev_facility_active",
            ),
            models.Index(
                fields=["status", "is_active"], name="idx_power_device_status"
            ),
        ]
