# facilities/models/facility.py
from django.conf import settings
from django.db import models
from django.utils import timezone


class Facility(models.Model):
    """
    공장 마스터 — 시스템 최상위 단위

    [Soft Delete 정책]
    공장은 물리적 삭제 금지. is_active=False로 비활성화.
    이유: 하위 센서·작업자·이벤트 이력 보존

    [manager FK 정책]
    manager는 SET_NULL — 담당 관리자 교체 시 공장은 유지
    NULL 허용: 공장 등록 후 관리자 배정 전 상태 표현

    [좌표계]
    공장별로 독립적인 도면 좌표계 사용 (픽셀 좌표)
    도면 해상도 변경 시 하위 좌표 일괄 환산 필요 (4차 과제)

    [타 앱 참조 확산]
    Facility는 5개 앱(facilities, geofence, positioning, alerts, safety)에서 FK 참조됨
    수정 시 영향 범위 확인 필요
    """

    name = models.CharField(max_length=200, verbose_name="공장 이름")
    address = models.CharField(max_length=500, verbose_name="공장 주소")

    # 도면 상 위치/크기 (지도 편집 관리에서 설정)
    map_x = models.FloatField(null=True, blank=True, verbose_name="도면 x 좌표 (px)")
    map_y = models.FloatField(null=True, blank=True, verbose_name="도면 y 좌표 (px)")
    map_width = models.FloatField(null=True, blank=True, verbose_name="도면 너비 (px)")
    map_height = models.FloatField(null=True, blank=True, verbose_name="도면 높이 (px)")
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_facilities",
        verbose_name="담당 관리자",
    )
    notes = models.TextField(blank=True, default="", verbose_name="비고")
    is_active = models.BooleanField(default=True, verbose_name="운영 여부")
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def deactivate(self):
        """공장 비활성화"""
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.save(update_fields=["is_active", "deactivated_at", "updated_at"])

    def __str__(self):
        return self.name

    class Meta:
        db_table = "facility"
        indexes = [
            models.Index(fields=["is_active"], name="idx_facility_active"),
        ]
