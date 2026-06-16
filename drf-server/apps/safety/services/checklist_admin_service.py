# safety/services/checklist_admin_service.py
"""
체크리스트 어드민 비즈니스 로직 — view에서 호출하는 서비스 함수 모음.

[발행 정책]
관리자가 [반영 저장]을 누르면 `publish_revision()`이 트랜잭션으로 스냅샷을 생성하고
기존 active Revision을 False로 전환한다. 현장 운영자 페이지는 active Revision의
`revision_data`를 읽어 렌더 (결정문 §3c-4 패턴).

[soft-delete + cascade]
섹션 삭제 시 하위 문항도 같은 timestamp로 함께 비활성화한다. 동일 timestamp는
"어느 시점에 묶여서 비활성화됐는지" 감사 추적성을 보장하기 위함 (이전 버그 fix).

[order 운영 규칙]
order 필드에 UniqueConstraint를 두지 않음. 드래그앤드롭 재정렬 시 일괄 UPDATE로
처리하므로 중간 충돌이 없고, 빈 자리(holes)가 생겨도 ordering 정렬에 무해.

[트랜잭션 일관성]
모든 mutating 함수에 `@transaction.atomic`. 특히 `publish_revision`은 partial
UniqueConstraint(facility, is_active=True) 위반 방지를 위해 기존 active를 먼저
False로 전환한 뒤 새 row를 INSERT하는 순서를 단일 트랜잭션 안에서 보장.
"""

from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.core.models import SystemLog
from apps.safety.models import (
    SafetyCheckItem,
    SafetyCheckSection,
    SafetyChecklistRevision,
)


class NoChangesToPublishError(Exception):
    """반영 저장 시점에 active revision과 내용이 동일해 새 버전 생성을 차단.

    view에서 잡아 400 + `code:"no_changes"`로 응답. 클라이언트는 "반영 보류"
    안내 다이얼로그를 표시하고 isDirty 플래그를 false로 리셋한다.
    """


# ──────────────────────────────────────────────────────────
# Section CRUD
# ──────────────────────────────────────────────────────────
@transaction.atomic
def create_section(
    facility_id: int,
    name: str,
    description: str = "",
    updated_by=None,
) -> SafetyCheckSection:
    """섹션 신규 생성. 활성 섹션 중 최대 order의 다음 값을 부여."""
    next_order = (
        SafetyCheckSection.objects.filter(
            facility_id=facility_id, is_active=True
        ).aggregate(m=Max("order"))["m"]
        or 0
    ) + 1
    return SafetyCheckSection.objects.create(
        facility_id=facility_id,
        name=name,
        description=description,
        order=next_order,
        updated_by=updated_by,
    )


@transaction.atomic
def update_section(
    section: SafetyCheckSection,
    *,
    name: str | None = None,
    description: str | None = None,
    updated_by=None,
) -> SafetyCheckSection:
    """섹션 부분 수정. None 인자는 "변경 없음" 의미 (description 비우기는 빈 문자열로)."""
    fields = ["updated_at"]
    if name is not None:
        section.name = name
        fields.append("name")
    if description is not None:
        section.description = description
        fields.append("description")
    if updated_by is not None:
        section.updated_by = updated_by
        fields.append("updated_by")
    section.save(update_fields=fields)
    return section


@transaction.atomic
def soft_delete_section(section: SafetyCheckSection, updated_by=None) -> None:
    """
    섹션 + 하위 활성 문항 일괄 비활성화.

    [감사 추적성]
    동일 timestamp(`now`)를 섹션과 하위 문항 모두에 적용해, "어느 시점에 함께
    비활성화됐는지"를 명확히 남긴다. 이전 구현은 items 업데이트 시점에 section의
    deactivated_at이 아직 None이라 하위 문항이 NULL로 비활성화되는 버그가 있었음.
    """
    now = timezone.now()
    SafetyCheckItem.objects.filter(section=section, is_active=True).update(
        is_active=False,
        deactivated_at=now,
    )
    section.is_active = False
    section.deactivated_at = now
    if updated_by is not None:
        section.updated_by = updated_by
    section.save(
        update_fields=["is_active", "deactivated_at", "updated_at", "updated_by"]
    )


@transaction.atomic
def reorder_sections(facility_id: int, ordered_ids: list[int]) -> None:
    """드래그앤드롭 후 일괄 order 갱신. 잘못된 id는 silent skip (입력 검증은 view 책임)."""
    for new_order, section_id in enumerate(ordered_ids, start=1):
        SafetyCheckSection.objects.filter(
            pk=section_id, facility_id=facility_id
        ).update(order=new_order)


# ──────────────────────────────────────────────────────────
# Item CRUD
# ──────────────────────────────────────────────────────────
@transaction.atomic
def create_item(
    section: SafetyCheckSection,
    title: str,
    description: str = "",
    is_required: bool = True,
    updated_by=None,
) -> SafetyCheckItem:
    """문항 신규 추가. 섹션 내 활성 문항 중 최대 order의 다음 값을 부여."""
    next_order = (
        SafetyCheckItem.objects.filter(section=section, is_active=True).aggregate(
            m=Max("order")
        )["m"]
        or 0
    ) + 1
    return SafetyCheckItem.objects.create(
        facility=section.facility,
        section=section,
        title=title,
        description=description,
        is_required=is_required,
        order=next_order,
        updated_by=updated_by,
    )


@transaction.atomic
def update_item(
    item: SafetyCheckItem,
    *,
    title: str | None = None,
    description: str | None = None,
    is_required: bool | None = None,
    updated_by=None,
) -> SafetyCheckItem:
    """문항 부분 수정. None 인자는 "변경 없음" 의미."""
    fields = ["updated_at"]
    if title is not None:
        item.title = title
        fields.append("title")
    if description is not None:
        item.description = description
        fields.append("description")
    if is_required is not None:
        item.is_required = is_required
        fields.append("is_required")
    if updated_by is not None:
        item.updated_by = updated_by
        fields.append("updated_by")
    item.save(update_fields=fields)
    return item


@transaction.atomic
def duplicate_item(item: SafetyCheckItem, updated_by=None) -> SafetyCheckItem:
    """동일 섹션 내 바로 다음 순번으로 사본 생성."""
    new_order = item.order + 1
    SafetyCheckItem.objects.filter(
        section=item.section, is_active=True, order__gte=new_order
    ).update(order=F("order") + 1)
    return SafetyCheckItem.objects.create(
        facility=item.facility,
        section=item.section,
        title=item.title,
        description=item.description,
        is_required=item.is_required,
        order=new_order,
        updated_by=updated_by,
    )


@transaction.atomic
def soft_delete_item(item: SafetyCheckItem, updated_by=None) -> None:
    """문항 단건 비활성화. 모델의 `deactivate()`가 deactivated_at=now 자동 세팅."""
    item.deactivate(updated_by=updated_by)


@transaction.atomic
def reorder_items(section_id: int, ordered_ids: list[int]) -> None:
    """섹션 내 문항 일괄 order 갱신. section_id에 속하지 않는 id는 silent skip."""
    for new_order, item_id in enumerate(ordered_ids, start=1):
        SafetyCheckItem.objects.filter(pk=item_id, section_id=section_id).update(
            order=new_order
        )


# ──────────────────────────────────────────────────────────
# Revision publish — [반영 저장]
# ──────────────────────────────────────────────────────────
def _build_revision_snapshot(facility_id: int) -> dict:
    """현재 활성 Section/Item을 JSON 스냅샷으로 직렬화.

    구조: `{"sections": [{"id","name","description","order","items":[
              {"id","title","description","is_required","order"}, ...
          ]}]}`
    이 dict가 그대로 `SafetyChecklistRevision.revision_data` JSONField에 저장되며,
    이후 동등성 비교(noop 발행 차단)와 운영자 페이지/이력 모달 렌더에 재사용된다.
    """
    sections = (
        SafetyCheckSection.objects.filter(facility_id=facility_id, is_active=True)
        .prefetch_related("items")
        .order_by("order", "id")
    )
    out = {"sections": []}
    for section in sections:
        items = [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "is_required": item.is_required,
                "order": item.order,
            }
            for item in section.items.filter(is_active=True).order_by("order", "id")
        ]
        out["sections"].append(
            {
                "id": section.id,
                "name": section.name,
                "description": section.description,
                "order": section.order,
                "items": items,
            }
        )
    return out


@transaction.atomic
def publish_revision(facility_id: int, user) -> SafetyChecklistRevision:
    """
    [반영 저장] — 스냅샷 1건 생성 + 기존 active를 False로 전환.

    UniqueConstraint(facility, is_active=True) 위반 방지를 위해 기존 row를
    먼저 False로 전환한 뒤 신규 row를 True로 INSERT (같은 트랜잭션).
    active revision과 내용이 동일하면 NoChangesToPublishError를 발생시켜
    의미 없는 새 버전 생성을 차단한다.
    """
    snapshot = _build_revision_snapshot(facility_id)

    active = SafetyChecklistRevision.objects.filter(
        facility_id=facility_id, is_active=True
    ).first()
    if active is not None and active.revision_data == snapshot:
        raise NoChangesToPublishError("변경 사항이 없어 새 버전을 생성하지 않았습니다.")

    SafetyChecklistRevision.objects.filter(
        facility_id=facility_id, is_active=True
    ).update(is_active=False)

    next_version = (
        SafetyChecklistRevision.objects.filter(facility_id=facility_id).aggregate(
            m=Max("version")
        )["m"]
        or 0
    ) + 1

    revision = SafetyChecklistRevision.objects.create(
        facility_id=facility_id,
        version=next_version,
        revision_data=snapshot,
        published_by=user if (user and user.is_authenticated) else None,
        is_active=True,
    )

    SystemLog.objects.create(
        actor=user if (user and user.is_authenticated) else None,
        action_type=SystemLog.ActionType.CHECKLIST_REVISION_PUBLISHED,
        target_model="SafetyChecklistRevision",
        target_id=str(revision.pk),
        target_name=f"facility {facility_id} / v{next_version}",
        new_value={"version": next_version},
    )
    return revision
