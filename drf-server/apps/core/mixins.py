# core/mixins.py
from django.db import models
from django.utils import timezone


class SoftDeleteMixin(models.Model):
    """
    Soft Delete 공통 동작

    적용 대상 판단:
    - 마스터 데이터이며 이력 보존이 중요 → 적용 권장
    - 예: Facility, GasSensor, PowerDevice, GeoFence, SafetyCheckItem

    미적용 대상:
    - CustomUser: AbstractUser.is_active 활용 (별도 정의)
    - 시계열/이벤트 데이터: Soft Delete 개념 없음
    - 불변 감사 로그: delete 자체를 차단 (오버라이드 활용)
    """

    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    def deactivate(self):
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.save(update_fields=["is_active", "deactivated_at"])

    def reactivate(self):
        self.is_active = True
        self.deactivated_at = None
        self.save(update_fields=["is_active", "deactivated_at"])

    class Meta:
        abstract = True


class TimestampMixin(models.Model):
    """생성·수정 타임스탬프 공통"""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
