from django.db import models

from apps.core.models.base import BaseModel


class RiskLevelStandard(BaseModel):
    """
    위험 단계 메타데이터 — RiskLevel 이넘과 1:1 강제 매핑

    [동기화 정책]
    code 값은 RiskLevel.values와 1:1 일치해야 함.
    fixture(apps/core/fixtures/risk_level_standard.json)로 초기 row 3개 강제 시드.
    어드민 폼에서 code 필드는 readonly — 운영자 임의 변경 차단.

    [메타 필드 분리]
    code/name은 비즈니스 핵심 분류 (코드 의존, 변경 금지)
    display_color는 운영자 자유 편집 (디자이너 hex 회신 시 마이그레이션 1회로 갱신)
    event_priority/alert_intensity는 백엔드 운영 정책 확정값
    """

    class AlertIntensity(models.TextChoices):
        NORMAL = "normal", "정상"
        WARNING = "warning", "주의"
        URGENT = "urgent", "긴급"

    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="위험 단계 코드",
        help_text="RiskLevel 이넘 값과 1:1 (normal/warning/danger)",
    )
    name = models.CharField(max_length=50, verbose_name="표시 명")
    display_color = models.CharField(
        max_length=20,
        default="green",
        verbose_name="표시 색상 토큰",
        help_text="green/orange/red 등 토큰명 — 디자이너 hex 회신 시 갱신",
    )
    alert_intensity = models.CharField(
        max_length=10,
        choices=AlertIntensity.choices,
        default=AlertIntensity.NORMAL,
        verbose_name="알림 강도",
    )
    event_priority = models.PositiveSmallIntegerField(
        default=1, verbose_name="이벤트 우선순위"
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.code} ({self.name})"

    class Meta:
        db_table = "risk_level_standard"
        ordering = ["event_priority"]
