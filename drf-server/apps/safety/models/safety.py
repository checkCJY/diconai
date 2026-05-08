# safety/models/safety.py
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models.base import BaseModel


class SafetyCheckItem(BaseModel):
    """
    체크리스트 항목 마스터

    [공장별 독립 관리]
    facility FK로 공장마다 자체 체크리스트 구성
    공장은 삭제되면 체크리스트 전체가 무의미 → CASCADE 허용 (예외)

    [order 운영 트랩]
    ⚠️ v2의 UniqueConstraint(facility, order)는 순서 변경 시 unique 충돌
    v4: unique 제거 + 서비스 레이어 일괄 UPDATE 패턴

    순서 변경 UX 예시 (드래그앤드롭):
    [old_order: 1, 2, 3] → [new_order: 1, 3, 2]
    방법:
    1. transaction.atomic 내부에서
    2. 전체 SafetyCheckItem을 필요한 order 값으로 한 번에 update
    3. unique 없으므로 중간 충돌 없음

    [Soft Delete]
    항목 삭제 시 SafetyStatus 이력 소멸 방지를 위해 Soft Delete
    is_active=False로 체크리스트에서 숨김, 과거 이력은 보존

    [is_required의 강제]
    is_required=True 항목 미체크 상태에서 "체크 완료" 처리 차단
    이 검증은 services/check_service.py에서 수행
    """

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.CASCADE,  # 공장 소멸 시 체크리스트도 소멸 (예외적 허용)
        related_name="safety_check_items",
    )
    # Phase 3-b: SafetyCheckSection 그룹화. 1단계 nullable → 2단계 백필 → 3단계 NOT NULL.
    # 모든 row가 facility별 "기본" Section으로 자동 매핑된 후 NOT NULL로 전환.
    section = models.ForeignKey(
        "safety.SafetyCheckSection",
        on_delete=models.PROTECT,
        related_name="items",
    )
    title = models.CharField(max_length=200, verbose_name="항목 제목")
    description = models.TextField(blank=True, default="", verbose_name="상세 설명")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="표시 순서")
    is_required = models.BooleanField(default=True, verbose_name="필수 여부")
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    # created_at / updated_at / updated_by 는 BaseModel 상속

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

    def __str__(self):
        return self.title

    class Meta:
        db_table = "safety_check_item"
        # ordering 기본 정렬은 유지 — 항목 수가 공장당 수십 개 수준이라 부담 없음
        ordering = ["order"]
        indexes = [
            models.Index(
                fields=["facility", "is_active", "order"],
                name="idx_scitem_fac_active_order",
            ),
        ]


class SafetyStatus(BaseModel):
    """
    작업자 체크 이력

    [Phase 3-c 변경 — 1세션 1항목으로 매일 체크 지원]
    이전 UNIQUE(worker, check_item) → UNIQUE(session, check_item)
    SafetyCheckSession 도입으로 (worker, date, revision) 단위 분리. 매일 체크 가능.

    [운영 방법]
    - 서비스 레이어 check_service.check_item()이 today 세션 get_or_create + mark_checked
    - mark_checked(session, note=None) — session 필수 키워드 인자

    [worker SET_NULL]
    CustomUser Soft Delete 정책 일관성
    worker=NULL은 탈퇴 작업자의 과거 체크 이력
    """

    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="safety_statuses",
    )
    check_item = models.ForeignKey(
        "safety.SafetyCheckItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="statuses",
    )
    # Phase 3-c: 5단계 마이그 완료 후 NOT NULL.
    # UNIQUE(session, check_item)이 (worker, check_item)을 대체.
    session = models.ForeignKey(
        "safety.SafetyCheckSession",
        on_delete=models.PROTECT,
        related_name="statuses",
    )
    check_item_title = models.CharField(
        max_length=200,
        verbose_name="체크 당시 항목 제목 (스냅샷)",
        help_text="항목이 삭제돼도 당시 제목 보존",
    )
    is_checked = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default="", verbose_name="작업자 메모")
    # created_at / updated_at / updated_by 는 BaseModel 상속

    def mark_checked(self, session, note: str | None = None):
        """
        체크 완료 처리 (Phase 3-c).

        [session 필수 키워드 인자] (결정문 §3c-8)
        session 도입 후 명시적 전달 — 자동 추론 금지 (silent error 위험).
        """
        from django.utils import timezone

        self.session = session
        self.is_checked = True
        self.checked_at = timezone.now()
        if note is not None:
            self.note = note
        self.save(
            update_fields=[
                "session",
                "is_checked",
                "checked_at",
                "note",
                "updated_at",
            ]
        )

    class Meta:
        db_table = "safety_status"
        constraints = [
            # Phase 3-c: 1인 1항목 고정 → 1세션 1항목 (매일 체크 지원)
            models.UniqueConstraint(
                fields=["session", "check_item"], name="uq_safety_session_item"
            ),
        ]
        indexes = [
            models.Index(
                fields=["worker", "-checked_at"], name="idx_safety_worker_time"
            ),
            models.Index(
                fields=["check_item", "is_checked"], name="idx_safety_item_checked"
            ),
        ]


# ──────────────────────────────────────────────────────────
# [4차 예정] DailySafetyRecord — 나중에 모델 변경 시 사용할 예정
# SafetyStatus UNIQUE(worker, check_item) 제약 해소 후 일별 이력 추적에 활용
# ──────────────────────────────────────────────────────────
# class DailySafetyRecord(models.Model):
#     worker = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True,
#         related_name="daily_safety_records",
#     )
#     date = models.DateField(verbose_name="확인 날짜")
#     checklist_done = models.BooleanField(default=False, verbose_name="체크리스트 완료")
#     vr_done = models.BooleanField(default=False, verbose_name="VR 교육 완료")
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#
#     class Meta:
#         db_table = "daily_safety_record"
#         unique_together = [("worker", "date")]
#         indexes = [
#             models.Index(fields=["worker", "-date"], name="idx_dsr_worker_date"),
#         ]
