# safety/selectors/checklist.py
"""
체크리스트 어드민·운영자 페이지용 읽기 쿼리 모음.

CLAUDE.md 컨벤션상 selector는 단순 조회·집계만 담당(쓰기 없음). 어드민 페이지의
좌측/우측 패널 데이터, 반영 이력 모달, "편집 중" 배지 신호가 모두 여기에서 나온다.

[변경 요약 계산기]
`compute_change_summary`는 현 revision의 `revision_data`와 직전 버전을 비교해
섹션/문항의 추가·수정·삭제 개수를 산출 — 반영 이력 모달 상단의 요약 카드 데이터.

[has_unpublished_changes의 휴리스틱 한계]
section/item의 `updated_at` 최댓값이 active.published_at보다 늦으면 True를 반환.
값을 원상복귀(예: 이름 A→B→A)하면 내용 동일이지만 timestamp 기준으로 True로 잡힘.
서버 측 noop 발행 차단(`active.revision_data == snapshot`)이 진짜 안전망 역할.
"""

from django.db.models import Max

from apps.safety.models import (
    SafetyCheckItem,
    SafetyCheckSection,
    SafetyChecklistRevision,
)


def get_sections_with_items(facility_id: int):
    """활성 섹션 + 활성 문항 트리 (order 정렬)."""
    return (
        SafetyCheckSection.objects.filter(facility_id=facility_id, is_active=True)
        .prefetch_related("items")
        .order_by("order", "id")
    )


def get_active_items_qs(section_id: int):
    """특정 섹션의 활성 문항 QuerySet (order 정렬)."""
    return SafetyCheckItem.objects.filter(
        section_id=section_id, is_active=True
    ).order_by("order", "id")


def get_active_revision(facility_id: int) -> SafetyChecklistRevision | None:
    """facility별 현재 활성 Revision (partial UniqueConstraint로 최대 1건 보장)."""
    return SafetyChecklistRevision.objects.filter(
        facility_id=facility_id, is_active=True
    ).first()


def list_revisions(facility_id: int):
    """반영 이력 모달 좌측 리스트 — 신규순."""
    return SafetyChecklistRevision.objects.filter(facility_id=facility_id).order_by(
        "-published_at"
    )


def get_revision(revision_id: int, facility_id: int) -> SafetyChecklistRevision | None:
    """facility 격리를 위해 facility_id를 함께 조건에 포함 (cross-facility 접근 차단)."""
    return SafetyChecklistRevision.objects.filter(
        pk=revision_id, facility_id=facility_id
    ).first()


def get_previous_revision(
    revision: SafetyChecklistRevision,
) -> SafetyChecklistRevision | None:
    """동일 facility의 직전 버전 (없으면 None — 최초 발행)."""
    return (
        SafetyChecklistRevision.objects.filter(
            facility_id=revision.facility_id, version__lt=revision.version
        )
        .order_by("-version")
        .first()
    )


def compute_change_summary(revision: SafetyChecklistRevision) -> dict:
    """
    직전 버전과 비교해 변경 개수 산출.
    이력 모달 상단 요약에 사용. 최초 발행이면 is_initial=True.
    """
    prev = get_previous_revision(revision)
    if prev is None:
        return {"is_initial": True}

    cur_data = revision.revision_data or {}
    prev_data = prev.revision_data or {}

    def index_sections(data):
        # id 기준 dict로 펼쳐 두 버전을 set 차집합/교집합으로 비교 가능하게 함.
        return {s["id"]: s for s in data.get("sections", []) if "id" in s}

    def index_items(data):
        # 문항은 섹션을 가로질러 평면화 (같은 문항이 다른 섹션으로 이동해도 id로 추적).
        out = {}
        for section in data.get("sections", []):
            for item in section.get("items", []):
                if "id" in item:
                    out[item["id"]] = item
        return out

    cur_sec = index_sections(cur_data)
    prev_sec = index_sections(prev_data)
    sec_added = len(set(cur_sec) - set(prev_sec))
    sec_removed = len(set(prev_sec) - set(cur_sec))
    sec_modified = 0
    for sid in set(cur_sec) & set(prev_sec):
        c, p = cur_sec[sid], prev_sec[sid]
        if c.get("name") != p.get("name") or c.get("description") != p.get(
            "description"
        ):
            sec_modified += 1

    cur_item = index_items(cur_data)
    prev_item = index_items(prev_data)
    item_added = len(set(cur_item) - set(prev_item))
    item_removed = len(set(prev_item) - set(cur_item))
    item_modified = 0
    for iid in set(cur_item) & set(prev_item):
        c, p = cur_item[iid], prev_item[iid]
        if (
            c.get("title") != p.get("title")
            or c.get("description") != p.get("description")
            or c.get("is_required") != p.get("is_required")
        ):
            item_modified += 1

    return {
        "is_initial": False,
        "previous_version": prev.version,
        "sections_added": sec_added,
        "sections_modified": sec_modified,
        "sections_removed": sec_removed,
        "items_added": item_added,
        "items_modified": item_modified,
        "items_removed": item_removed,
    }


def has_unpublished_changes(facility_id: int) -> bool:
    """
    "편집 중" 배지 조건.
    활성 Revision의 published_at 이후 Section/Item이 수정·생성됐는지 판단.
    활성 Revision이 없으면(최초 발행 전) 데이터가 1건이라도 있으면 True.
    """
    active = get_active_revision(facility_id)
    section_qs = SafetyCheckSection.objects.filter(facility_id=facility_id)
    item_qs = SafetyCheckItem.objects.filter(facility_id=facility_id)
    if active is None:
        return section_qs.exists() or item_qs.exists()

    last_section_change = section_qs.aggregate(m=Max("updated_at"))["m"]
    last_item_change = item_qs.aggregate(m=Max("updated_at"))["m"]
    candidates = [t for t in (last_section_change, last_item_change) if t is not None]
    if not candidates:
        return False
    return max(candidates) > active.published_at
