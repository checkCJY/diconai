# safety/models/safety.py
from django.db import models
from django.utils import timezone
from django.conf import settings


class SafetyCheckItem(models.Model):
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
    title = models.CharField(max_length=200, verbose_name="항목 제목")
    description = models.TextField(blank=True, default="", verbose_name="상세 설명")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="표시 순서")
    is_required = models.BooleanField(default=True, verbose_name="필수 여부")
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def deactivate(self):
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.save(update_fields=["is_active", "deactivated_at", "updated_at"])

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


class SafetyStatus(models.Model):
    """
    작업자 체크 이력

    [⚠️ 3차 한계 — 1인 1항목 영구 고정]
    복합 UNIQUE (worker, check_item) 때문에 "매일 체크" 불가능
    한 작업자가 한 항목을 한 번만 체크 가능, 이력 누적 불가

    이 제약은 규제 대응(일일 점검 의무)과 충돌하며, 4차에 해결 예정:
    - SafetyCheckSession 모델 추가 (session, date 기반 관리)
    - SafetyStatus.session FK 도입 → UNIQUE(session, check_item)
    - 1일 1세션으로 "매일 체크" 지원

    [3차 운영 방법]
    - 작업자가 항목을 체크 → SafetyStatus 1개 생성 (is_checked=True)
    - 재체크 시 기존 레코드의 checked_at만 업데이트 (UNIQUE 위반 방지)
    - "오늘 체크 여부"는 checked_at의 날짜로만 판단

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
    check_item_title = models.CharField(
        max_length=200,
        verbose_name="체크 당시 항목 제목 (스냅샷)",
        help_text="항목이 삭제돼도 당시 제목 보존",
    )
    is_checked = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default="", verbose_name="작업자 메모")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_checked(self, note: str = ""):
        from django.utils import timezone

        self.is_checked = True
        self.checked_at = timezone.now()
        if note:
            self.note = note
        self.save(update_fields=["is_checked", "checked_at", "note", "updated_at"])

    class Meta:
        db_table = "safety_status"
        constraints = [
            # 3차 제약 — 1인 1항목 고정
            models.UniqueConstraint(
                fields=["worker", "check_item"], name="uq_safety_worker_item"
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
