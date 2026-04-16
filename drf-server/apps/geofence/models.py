# Create your models here.
from django.db import models


class GeoFence(models.Model):
    """
    위험구역 — 공장 지도 위 다각형
    단순 화면 요소가 아닌 서버 판단 로직의 기준 데이터
    is_active로 삭제 대신 비활성화 — 과거 알람 이력 연결 보존
    """

    class ZoneType(models.TextChoices):
        DANGER  = 'danger',  '위험구역'
        WARNING = 'warning', '주의구역'
        NORMAL  = 'normal',  '안전구역'

    class RiskLevel(models.IntegerChoices):
        NORMAL  = 0, '정상'
        WARNING = 1, '주의'
        DANGER  = 2, '위험'

    facility    = models.ForeignKey(
        'sensors.Facility',
        on_delete=models.CASCADE,
        related_name='geo_fences'
    )
    name        = models.CharField(max_length=50)
    zone_type   = models.CharField(
        max_length=100,
        choices=ZoneType.choices
    )
    polygon     = models.JSONField()
    risk_level  = models.IntegerField(
        choices=RiskLevel.choices,
        default=RiskLevel.NORMAL
    )
    description = models.TextField(null=True, blank=True)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.zone_type})"

    class Meta:
        db_table = 'geo_fence'
        ordering = ['name']


class WorkerPosition(models.Model):
    """
    작업자 실시간 위치 기록
    current_geofence 캐싱으로 매번 polygon 재계산 없이 구역 판단 가능
    measured_at vs received_at 듀얼 타임스탬프로 통신 지연 감지
    """

    class MovementStatus(models.TextChoices):
        MOVING      = 'moving',      '이동 중'
        STATIONARY  = 'stationary',  '정지'
        IDLE        = 'idle',        '대기'

    worker              = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.CASCADE,
        related_name='positions'
    )
    current_geofence    = models.ForeignKey(
        GeoFence,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='worker_positions'
    )
    x                   = models.FloatField()
    y                   = models.FloatField()
    movement_status     = models.CharField(
        max_length=100,
        choices=MovementStatus.choices,
        default=MovementStatus.MOVING
    )
    measured_at         = models.DateTimeField()
    received_at         = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.worker.username} - ({self.x}, {self.y})"

    class Meta:
        db_table = 'worker_position'
        ordering = ['-measured_at']
        indexes = [
            models.Index(
                fields=['worker', '-measured_at'],
                name='idx_wpos_time'
            )
        ]