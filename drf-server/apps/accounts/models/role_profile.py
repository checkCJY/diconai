from django.db import models

from apps.core.constants import UserType
from apps.core.models.base import BaseModel


class RoleProfile(BaseModel):
    """
    역할 프로파일 — UserType 4종 외 사용자 정의 역할

    [현재 사용]
    Phase 1에서는 모델만 신설. CustomUser와의 연결은 Phase 2 이후
    화면 요구가 들어올 때 추가.

    [base_user_type]
    이 RoleProfile을 부여받은 사용자의 user_type 추론용.
    권한 검사 시 매핑 기준.

    [platform_type]
    웹 어드민 전용 역할인지 모바일 앱 사용자인지 구분.
    Menu/RoleMenuVisibility(Phase 2-c)에서 활용.
    """

    PLATFORM_CHOICES = [
        ("web", "웹 어드민"),
        ("app", "모바일 앱"),
    ]

    code = models.CharField(max_length=50, unique=True, verbose_name="역할 코드")
    name = models.CharField(max_length=100, verbose_name="역할 명")
    base_user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        verbose_name="기반 사용자 유형",
    )
    platform_type = models.CharField(
        max_length=10,
        choices=PLATFORM_CHOICES,
        default="web",
        verbose_name="플랫폼",
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.name})"

    class Meta:
        db_table = "role_profile"
        ordering = ["code"]
