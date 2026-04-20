# safety/services/check_service.py

from django.db import transaction
from safety.models import SafetyCheckItem, SafetyStatus


@transaction.atomic
def check_item(worker_id: int, item_id: int, note: str = ""):
    """
    항목 체크 처리 — 기존 레코드 있으면 업데이트, 없으면 생성
    """
    item = SafetyCheckItem.objects.get(pk=item_id, is_active=True)

    status, created = SafetyStatus.objects.get_or_create(
        worker_id=worker_id,
        check_item=item,
        defaults={"check_item_title": item.title},
    )
    status.mark_checked(note=note)
    return status


def can_complete_session(worker_id: int, facility_id: int) -> bool:
    """
    필수 항목 전부 체크 여부 확인
    is_required=True 항목 중 is_checked=False가 없으면 True
    """
    required_items = SafetyCheckItem.objects.filter(
        facility_id=facility_id,
        is_active=True,
        is_required=True,
    )
    for item in required_items:
        status = SafetyStatus.objects.filter(
            worker_id=worker_id,
            check_item=item,
            is_checked=True,
        ).first()
        if not status:
            return False
        # 3차 한계: 날짜 기준 오늘 체크 여부
        from django.utils import timezone

        if status.checked_at.date() != timezone.now().date():
            return False
    return True


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
