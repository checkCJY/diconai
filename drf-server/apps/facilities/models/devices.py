# facilities/models/devices.py
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models.base import BaseModel


class DeviceBase(BaseModel):
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
    # created_at / updated_at / updated_by 는 BaseModel 상속

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

    [센서 ID 규칙]
    GAS-{device_code} 형태 (예: GAS-001). device_code는 등록 시 자동 부여.

    [좌표계]
    x, y는 facility의 공장 도면 픽셀 좌표 (좌상단 원점)

    [상태 관리]
    - NORMAL: 정상 수신 중
    - OFFLINE: last_reading 기준 5분 이상 미수신
    - ERROR: 센서 하드웨어 이상
    - INACTIVE: 철거/교체로 비활성화
    """

    device_code = models.CharField(max_length=10, unique=True, verbose_name="장비 코드")
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gas_sensors",
        verbose_name="관리 부서",
    )
    manager = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_gas_sensors",
        verbose_name="관리 담당자",
    )
    ip_address = models.CharField(
        max_length=45, blank=True, default="", verbose_name="통신 IP"
    )
    port = models.PositiveIntegerField(null=True, blank=True, verbose_name="통신 PORT")
    connection_checked_at = models.DateTimeField(
        null=True, blank=True, verbose_name="마지막 연결 확인일시"
    )
    connection_ok = models.BooleanField(
        null=True, blank=True, verbose_name="연결 확인 결과"
    )
    notes = models.TextField(blank=True, default="", verbose_name="비고")

    @property
    def sensor_id(self):
        if self.device_code:
            return f"GAS-{self.device_code}"
        return self.device_name

    def __str__(self):
        return f"{self.sensor_id} ({self.device_id})"

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
    전력 장비 마스터 — 스마트 전력 시스템 관리

    [장비 코드 규칙]
    PWR-{device_code} 형태 (예: PWR-001). device_code는 등록 시 자동 부여.

    [상태 관리]
    - NORMAL: 정상 수신 중
    - OFFLINE: last_reading 기준 5분 이상 미수신
    - ERROR: 장비 하드웨어 이상
    - INACTIVE: 철거/교체로 비활성화
    """

    channel_count = models.PositiveSmallIntegerField(default=16, verbose_name="채널 수")
    channel_meta = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="채널 메타데이터",
    )
    device_code = models.CharField(max_length=10, unique=True, verbose_name="장비 코드")
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="power_devices",
        verbose_name="관리 부서",
    )
    manager = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_power_devices",
        verbose_name="관리 담당자",
    )
    ip_address = models.CharField(
        max_length=45, blank=True, default="", verbose_name="통신 IP"
    )
    port = models.PositiveIntegerField(null=True, blank=True, verbose_name="통신 PORT")
    connection_checked_at = models.DateTimeField(
        null=True, blank=True, verbose_name="마지막 연결 확인일시"
    )
    connection_ok = models.BooleanField(
        null=True, blank=True, verbose_name="연결 확인 결과"
    )
    notes = models.TextField(blank=True, default="", verbose_name="비고")

    @property
    def power_id(self):
        if self.device_code:
            return f"PWR-{self.device_code}"
        return self.device_name

    def __str__(self):
        return f"{self.power_id} ({self.device_id})"

    def get_channel_label(self, channel: int) -> str:
        """채널별 사용자 친화 라벨.

        channel_meta[str(channel)]["name"] 우선 (운영자 등록 시 "송풍기A" 등),
        미지정 시 "CH{N}" 폴백. monitoring/services/power_alarm._channel_label 과
        AlarmRecord.get_short_message 양쪽이 본 메서드를 호출 — 라벨 규칙 단일화.
        """
        meta = (self.channel_meta or {}).get(str(channel)) or {}
        return meta.get("name") or f"CH{channel}"

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
                fields=["facility", "is_active"], name="idx_pwrdev_facility_active"
            ),
            models.Index(
                fields=["status", "is_active"], name="idx_power_device_status"
            ),
        ]
