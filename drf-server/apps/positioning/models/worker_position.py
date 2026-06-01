# positioning/models/worker_position.py
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class WorkerPosition(models.Model):
    """
    작업자 실시간 위치 기록 + 현재 구역 캐시

    [current_geofence 캐싱 정책]
    위치 수신 시마다 update_geofence_cache() 호출
    GeoFence.polygon 변경 시 해당 공장 전체 작업자 캐시 무효화 필요
    → recalculate_worker_positions_for_facility()

    [좌표계]
    x, y: facility의 공장 도면 픽셀 좌표 (GasSensor, GeoFence와 동일 좌표계)
    facility가 다르면 좌표계도 다름 — 반드시 facility와 함께 해석

    [통신 지연 정책]
    (received_at - measured_at) > 5분이면 current_geofence 갱신 스킵
    이력은 저장하되 현재 구역 판정에는 미사용 (is_stale property)

    [작업자 탈퇴 정책]
    worker: SET_NULL — CustomUser.deactivate() 정책과 일관
    worker=NULL 레코드 = 탈퇴 작업자 이력 (사고 조사/감사 대응)

    [대용량 대응]
    작업자 50명 × 30초 주기 가정 시 연간 약 5,256만 행. 현재는 파티셔닝 없이
    운영하고, 규모 확대 시 TimescaleDB 또는 월별 파티션 도입 예정.
    """

    class MovementStatus(models.TextChoices):
        MOVING = "moving", "이동 중"
        STATIONARY = "stationary", "정지"
        IDLE = "idle", "대기"

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="worker_positions",
        db_index=True,
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="positions",
    )
    current_geofence = models.ForeignKey(
        "geofence.GeoFence",  # 타 앱 참조
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worker_positions",
    )
    # 수신 노드 FK — 어떤 PositionNode가 본 좌표를 측정·전송했는지 기록.
    # nullable: 펌웨어 페이로드 갱신 전 row + node_id 미상 케이스 보존
    received_node = models.ForeignKey(
        "facilities.PositionNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_positions",
        verbose_name="수신 노드",
    )
    x = models.FloatField(verbose_name="x 좌표")
    y = models.FloatField(verbose_name="y 좌표")
    movement_status = models.CharField(
        max_length=20,
        choices=MovementStatus.choices,
        default=MovementStatus.MOVING,
    )
    measured_at = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)

    @property
    def communication_delay_seconds(self) -> float:
        if not self.measured_at or not self.received_at:
            return 0.0
        return (self.received_at - self.measured_at).total_seconds()

    @property
    def is_stale(self) -> bool:
        """5분 이상 지연된 위치 데이터 여부"""
        return self.communication_delay_seconds > 300

    def update_geofence_cache(self):
        """
        현재 좌표 기준 current_geofence 캐시 갱신
        - 지연 데이터(is_stale=True)는 스킵
        - 여러 구역 겹칠 시 risk_level 높은 구역 우선
        - 실제 Point-in-Polygon 로직은 geofence 앱의 selector 활용
        """
        if self.is_stale:
            self.current_geofence = None
            return
        from apps.geofence.selectors.geofence_candidates import (
            find_geofence_containing_point,
        )

        self.current_geofence = find_geofence_containing_point(
            facility_id=self.facility_id,
            x=self.x,
            y=self.y,
        )

    def clean(self):
        """좌표 유효성 검증"""
        if self.x < 0 or self.y < 0:
            raise ValidationError(f"좌표는 0 이상이어야 합니다: ({self.x}, {self.y})")

    def __str__(self):
        name = self.worker.username if self.worker else "(탈퇴)"
        return f"{name} @ ({self.x}, {self.y}) [{self.measured_at}]"

    class Meta:
        db_table = "worker_position"
        indexes = [
            models.Index(fields=["worker", "-measured_at"], name="idx_wp_worker_time"),
            models.Index(
                fields=["facility", "-measured_at"], name="idx_wp_facility_time"
            ),
            models.Index(
                fields=["current_geofence", "-measured_at"], name="idx_wp_geofence_time"
            ),
        ]
