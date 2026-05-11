from django.db import models

from apps.core.models.base import BaseModel


class Menu(BaseModel):
    """
    메뉴 마스터 — dashboard SNB(사이드바) + 어드민 메뉴 DB 관리

    [기존 코드와의 관계]
    Phase 2 시점에는 모델 + 시드만 신설. dashboard/views.py의 get_menu_tree(role)
    DB 조회 전환은 Phase 4-a. 그동안 menu.py 하드코딩과 본 모델 시드는 동일 데이터
    (snake_case 코드 변환).

    [code 형식]
    snake_case로 통일 (CodeGroup.code, RoleProfile.code 등 다른 코드값과 일관).
    예: dashboard_main, equipment_management.
    """

    class MenuType(models.TextChoices):
        SNB = "snb", "사이드바"
        ADMIN = "admin", "어드민"

    code = models.CharField(max_length=50, unique=True, verbose_name="메뉴 코드")
    name = models.CharField(max_length=100, verbose_name="표시 명")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    menu_type = models.CharField(
        max_length=20, choices=MenuType.choices, default=MenuType.SNB
    )
    sort_order = models.PositiveIntegerField(default=0)
    icon = models.CharField(max_length=50, blank=True, default="")
    url_path = models.CharField(max_length=200, blank=True, default="")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.name})"

    class Meta:
        db_table = "menu"
        ordering = ["sort_order", "code"]
        indexes = [
            models.Index(fields=["menu_type", "sort_order"]),
            models.Index(fields=["parent", "sort_order"]),
        ]
