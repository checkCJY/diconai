# geofence/models/geofence.py
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.constants import RiskLevel


def validate_polygon(data):
    """polygon JSON 구조 검증"""
    if not isinstance(data, list):
        raise ValidationError("polygon은 좌표 배열이어야 합니다.")
    if len(data) < 3:
        raise ValidationError(f"다각형은 최소 3개 꼭짓점 필요: 현재 {len(data)}개")
    for i, point in enumerate(data):
        if not (isinstance(point, list) and len(point) == 2):
            raise ValidationError(f"{i}번째 꼭짓점이 [x, y] 형식이 아닙니다.")
        if not all(isinstance(c, (int, float)) for c in point):
            raise ValidationError(f"{i}번째 꼭짓점에 숫자가 아닌 값이 있습니다.")


class GeoFence(models.Model):
    """
    위험구역 다각형 — 서버 판정 로직의 기준 데이터

    [polygon 스키마]
    공장 도면 픽셀 좌표 배열 (좌상단 원점)
    형식: [[x1, y1], [x2, y2], ..., [xN, yN]] — 닫힌 다각형
    예시: [[100, 200], [150, 250], [100, 300], [50, 250]]
    수신 시 validate_polygon()으로 구조 검증

    [Soft Delete 정책]
    is_active=False로 비활성화 (물리 삭제 금지)
    이유: 과거 AlarmRecord, Event, WorkerPosition의 geofence FK 참조 유지

    [risk_level 통일]
    v2의 zone_type + risk_level 이중 관리 제거
    RiskLevel TextChoices로 통일 (core.constants)

    [polygon 변경과 캐시 무효화]
    polygon이 수정되면 해당 공장의 모든 활성 WorkerPosition의
    current_geofence 캐시가 실제 위치와 불일치 가능
    → geofence/services/geofence_service.py의 update_polygon()
      함수가 변경 시 positioning 앱에 캐시 재계산을 트리거
    """

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, related_name="geo_fences"
    )
    name = models.CharField(max_length=50, verbose_name="구역 이름")
    polygon = models.JSONField(
        validators=[validate_polygon], verbose_name="꼭짓점 좌표 배열"
    )
    risk_level = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.NORMAL,
        verbose_name="위험도",
    )
    description = models.TextField(blank=True, default="", verbose_name="설명")
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def contains_point(self, x: float, y: float) -> bool:
        """좌표 (x, y)가 이 polygon 내부에 있는지 판정 (Ray casting)"""
        vertices = self.polygon
        num_vertices = len(vertices)
        is_inside = False
        prev_idx = num_vertices - 1
        for curr_idx in range(num_vertices):
            curr_x, curr_y = vertices[curr_idx]
            prev_x, prev_y = vertices[prev_idx]
            crosses_ray_y = (curr_y > y) != (prev_y > y)
            intersection_x = (prev_x - curr_x) * (y - curr_y) / (
                prev_y - curr_y
            ) + curr_x
            if crosses_ray_y and (x < intersection_x):
                is_inside = not is_inside
            prev_idx = curr_idx
        return is_inside

    def deactivate(self):
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.save(update_fields=["is_active", "deactivated_at", "updated_at"])

    def clean(self):
        validate_polygon(self.polygon)

    def __str__(self):
        return f"{self.name} ({self.risk_level})"

    class Meta:
        db_table = "geo_fence"
        indexes = [
            models.Index(
                fields=["facility", "is_active"], name="idx_geofence_facility_active"
            ),
            models.Index(
                fields=["risk_level", "is_active"], name="idx_geofence_risk_active"
            ),
        ]
