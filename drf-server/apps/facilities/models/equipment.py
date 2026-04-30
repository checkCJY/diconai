from django.db import models
from django.utils import timezone


class Equipment(models.Model):
    """
    설비 마스터 — 공장(Facility)과 전력 장치(PowerDevice) 사이의 1:1 매핑 단위

    [설비코드]
    EQP-{id:03d} 형태로 자동 생성 (수동 지정 불가)

    [연결 정책]
    power_device는 OneToOneField로 1:1 관계 보장
    장치 미연결 상태(null)로 등록 후 나중에 연결 가능

    [Soft Delete]
    물리 삭제 금지, is_active=False로 비활성화
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def equipment_code(self):
        return f"EQP-{self.id:03d}"

    def deactivate(self):
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.save(update_fields=["is_active", "deactivated_at", "updated_at"])
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
