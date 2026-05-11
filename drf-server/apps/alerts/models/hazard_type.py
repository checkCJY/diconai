from django.db import models

from apps.core.models.base import BaseModel


class HazardType(BaseModel):
    """
    위험 유형 — AlarmType 이넘과 1:1 강제 매핑 (UI 관리용 메타)

    [동기화 정책]
    type_code 값은 AlarmType.values와 1:1 일치해야 함.
    fixture(apps/alerts/fixtures/hazard_type.json)로 초기 row 시드.
    CI 정합성 테스트 (test_alarm_type_consistency)가 PR 단계에서 어긋남 차단.

    [코드 이넘과의 분리]
    AlarmType은 코드 분기에 사용 (1차 진실 공급원).
    HazardType은 운영자 어드민 UI 편집용 (라벨/색상/그룹/지도 표시 여부).
    """

    group = models.ForeignKey(
        "alerts.HazardTypeGroup",
        on_delete=models.PROTECT,
        related_name="types",
    )
    type_code = models.CharField(max_length=50, unique=True, verbose_name="유형 코드")
    name = models.CharField(max_length=100, verbose_name="표시 명")
    display_color = models.CharField(
        max_length=20, default="orange", verbose_name="표시 색상 토큰"
    )
    map_visible = models.BooleanField(default=True, verbose_name="지도 표시 여부")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.type_code} ({self.name})"

    class Meta:
        db_table = "hazard_type"
        ordering = ["group__sort_order", "type_code"]
