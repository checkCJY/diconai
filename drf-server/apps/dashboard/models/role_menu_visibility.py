from django.db import models

from apps.core.models.base import BaseModel


class RoleMenuVisibility(BaseModel):
    """
    역할별 메뉴 노출 매핑 — RoleProfile × Menu

    [기본 정책]
    매핑 없으면 비노출. is_visible=True 인 row만 화면에 표시.
    Phase 4-a에서 get_menu_tree(role) → DB 조회로 전환 시 본 매핑 사용.
    """

    role_profile = models.ForeignKey(
        "accounts.RoleProfile",
        on_delete=models.CASCADE,
        related_name="menu_visibilities",
    )
    menu = models.ForeignKey(
        "dashboard.Menu",
        on_delete=models.CASCADE,
        related_name="role_visibilities",
    )
    is_visible = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.role_profile.code} → {self.menu.code} ({self.is_visible})"

    class Meta:
        db_table = "role_menu_visibility"
        constraints = [
            models.UniqueConstraint(
                fields=["role_profile", "menu"], name="uq_rolemenu"
            ),
        ]
        indexes = [
            models.Index(fields=["role_profile", "is_visible"]),
        ]
