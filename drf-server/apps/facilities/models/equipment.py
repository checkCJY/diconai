from django.db import models
from django.utils import timezone

from apps.core.models.base import BaseModel


class Equipment(BaseModel):
    """
    설비 마스터 — 공장(Facility)과 전력 장치(PowerDevice) 사이의 1:1 매핑 단위

    [설비코드]
    FAC-{id:03d} 형태로 자동 생성 (수동 지정 불가)
    피그마 화면 표기 통일을 위해 EQP- → FAC- 로 변경 (4차)

    [연결 정책]
    power_device는 OneToOneField로 1:1 관계 보장
    장치 미연결 상태(null)로 등록 후 나중에 연결 가능

    [Soft Delete]
    물리 삭제 금지, is_active=False로 비활성화

    [updated_by 추적]
    BaseModel 상속으로 created_at/updated_at/updated_by 자동 추적.
    write view에서 serializer.save(updated_by=request.user) 또는
    deactivate(updated_by=request.user) 호출 필요.
    """

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="equipments",
        verbose_name="소속 공장",
    )
    power_device = models.OneToOneField(
        "facilities.PowerDevice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="equipment",
        verbose_name="연결 전력 장치",
    )
    name = models.CharField(max_length=200, verbose_name="설비명")
    notes = models.TextField(blank=True, default="", verbose_name="비고")
    is_active = models.BooleanField(default=True, verbose_name="사용 여부")
    deactivated_at = models.DateTimeField(null=True, blank=True)

    @property
    def equipment_code(self):
        return f"FAC-{self.id:03d}"

    def deactivate(self, updated_by=None):
        self.is_active = False
        self.deactivated_at = timezone.now()
        if updated_by is not None:
            self.updated_by = updated_by
        self.save(
            update_fields=[
                "is_active",
                "deactivated_at",
                "updated_at",
                "updated_by",
            ]
        )
        if self.power_device_id:
            self.power_device.deactivate()

    def __str__(self):
        return f"{self.equipment_code} {self.name}"

    class Meta:
        db_table = "equipment"
        indexes = [
            models.Index(
                fields=["facility", "is_active"], name="idx_equipment_facility_active"
            ),
        ]
