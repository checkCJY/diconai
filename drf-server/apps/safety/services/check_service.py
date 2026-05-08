# safety/services/check_service.py

from django.db import transaction
from django.utils import timezone

from apps.safety.models import (
    SafetyCheckItem,
    SafetyChecklistRevision,
    SafetyCheckSession,
    SafetyStatus,
)


def get_or_create_today_session(worker_id: int, facility_id: int) -> SafetyCheckSession:
    """
    Phase 3-c: (worker, date=today, revision=current_active) 세션 get_or_create.

    facility의 active Revision 1개를 조회 → 오늘 작업분 세션 반환.
    같은 날 두 번 호출 → 기존 세션 이어가기 (결정문 §3c-2).
    """
    revision = SafetyChecklistRevision.objects.filter(
        facility_id=facility_id, is_active=True
    ).first()
    if revision is None:
        raise ValueError(
            f"facility {facility_id}에 활성 Revision이 없습니다. 먼저 발행하세요."
        )
    session, _ = SafetyCheckSession.objects.get_or_create(
        worker_id=worker_id,
        date=timezone.now().date(),
        revision=revision,
    )
    return session


@transaction.atomic
def check_item(worker_id: int, item_id: int, note: str = ""):
    """
    항목 체크 처리 — Phase 3-c 시그니처 변경.
    UNIQUE(session, check_item)로 전환되어 1세션당 1체크. 같은 날 재체크는
    기존 row의 checked_at만 갱신 (mark_checked 내부에서 처리).
    """
    item = SafetyCheckItem.objects.get(pk=item_id, is_active=True)
    session = get_or_create_today_session(
        worker_id=worker_id, facility_id=item.facility_id
    )

    status, _ = SafetyStatus.objects.get_or_create(
        session=session,
        check_item=item,
        defaults={
            "worker_id": worker_id,
            "check_item_title": item.title,
        },
    )
    status.mark_checked(session=session, note=note)
    return status


def can_complete_session(worker_id: int, facility_id: int) -> bool:
    """
    필수 항목 전부 체크 여부 확인 — Phase 3-c session 기반으로 단순화.
    오늘 세션 내에서 모든 필수 Item이 체크됐는지 확인.
    """
    revision = SafetyChecklistRevision.objects.filter(
        facility_id=facility_id, is_active=True
    ).first()
    if revision is None:
        return False
    session = SafetyCheckSession.objects.filter(
        worker_id=worker_id,
        date=timezone.now().date(),
        revision=revision,
    ).first()
    if session is None:
        return False
    required_item_ids = set(
        SafetyCheckItem.objects.filter(
            facility_id=facility_id, is_active=True, is_required=True
        ).values_list("id", flat=True)
    )
    checked_item_ids = set(
        SafetyStatus.objects.filter(session=session, is_checked=True).values_list(
            "check_item_id", flat=True
        )
    )
    return required_item_ids.issubset(checked_item_ids)


@transaction.atomic
def reorder_items(facility_id: int, ordered_item_ids: list[int]):
    """
    체크리스트 순서 변경 (드래그앤드롭 후 저장)
    ordered_item_ids의 인덱스를 order 값으로 사용
    """
    for new_order, item_id in enumerate(ordered_item_ids):
        SafetyCheckItem.objects.filter(pk=item_id, facility_id=facility_id).update(
            order=new_order
        )
