from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models.base import BaseModel


class SafetyChecklistRevision(BaseModel):
    """
    체크리스트 개정 — 발행 시점 동결 스냅샷 (Phase 3-c)

    [발행 정책]
    관리자 수동 "발행" 버튼 (결정문 §3c-4). SystemLog는 ActionType
    `CHECKLIST_REVISION_PUBLISHED`로 기록.

    [revision_data JSON 스냅샷]
    Section 트리 + Item 메타(title/is_required/order). 발행 후 SafetyCheckItem
    변경/삭제에도 과거 Revision 불변 — 감사 요구 충족.
    구조:
        {
            "sections": [
                {"id": 1, "name": "...", "order": 1, "items": [
                    {"id": 10, "title": "...", "is_required": true, "order": 1},
                    ...
                ]},
                ...
            ]
        }

    [is_active]
    facility별 1개 active만 허용 (부분 UniqueConstraint).
    새 Revision 발행 시 기존 active를 False로, 새 row를 True로 전환.
    """

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="checklist_revisions",
    )
    version = models.PositiveIntegerField(
        verbose_name="버전 번호",
        help_text="공장별 1, 2, 3, ... 자동 부여 (서비스 레이어에서 max+1)",
    )
    revision_data = models.JSONField(
        default=dict,
        verbose_name="개정 스냅샷",
        help_text="발행 시점 Section 트리 + Item 메타",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_revisions",
    )
    published_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(
        default=True,
        verbose_name="활성 개정",
        help_text="facility별 1개만 True (부분 UniqueConstraint)",
    )

    def __str__(self):
        return f"{self.facility_id}/v{self.version}"

    class Meta:
        db_table = "safety_checklist_revision"
        ordering = ["facility", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "version"],
                name="uq_revision_facility_version",
            ),
            # facility별 활성 개정 1개만 (PostgreSQL 부분 인덱스)
            models.UniqueConstraint(
                fields=["facility"],
                condition=Q(is_active=True),
                name="uq_revision_facility_active",
            ),
        ]
        indexes = [
            models.Index(
                fields=["facility", "is_active"],
                name="idx_revision_fac_active",
            ),
        ]
