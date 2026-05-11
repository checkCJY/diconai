from django.conf import settings
from django.db import models

from apps.core.models.base import BaseModel


class SafetyCheckSession(BaseModel):
    """
    안전 체크 세션 — 1일 1세션 단위 (Phase 3-c)

    [복합 UNIQUE: (worker, date, revision)]
    같은 날 개정 발행 시 worker별 v1/v2 충돌 방지 (결정문 §3c-1).
    "오늘 이미 체크"는 (worker, date, current_active_revision) 조회로 판정.

    [1일 1세션 정책]
    같은 날 worker가 두 번 시작하면 기존 세션 이어가기 (결정문 §3c-2).
    재시작/reset 안 함 — 데이터 일관성.

    [worker SET_NULL]
    CustomUser Soft Delete 정책 일관. 탈퇴 작업자 과거 세션 보존.
    """

    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="safety_sessions",
    )
    date = models.DateField(verbose_name="작업일")
    revision = models.ForeignKey(
        "safety.SafetyChecklistRevision",
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    is_completed = models.BooleanField(
        default=False, verbose_name="완료 여부 (모든 필수 항목 체크)"
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        worker_name = self.worker.username if self.worker else "(탈퇴)"
        return f"{worker_name} @ {self.date} (rev={self.revision_id})"

    class Meta:
        db_table = "safety_check_session"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "date", "revision"],
                name="uq_session_worker_date_revision",
            ),
        ]
        indexes = [
            models.Index(fields=["worker", "-date"], name="idx_session_worker_date"),
            models.Index(
                fields=["revision", "-date"], name="idx_session_revision_date"
            ),
        ]
