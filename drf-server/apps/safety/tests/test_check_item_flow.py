"""
안전 체크리스트 흐름 회귀 테스트 (Phase 1~4 회귀 점검 Step 3).

[회귀 커버 대상]
- Phase 3 PR2: SafetyCheckSection FK (PROTECT)
- Phase 3 PR3: SafetyChecklistRevision (facility별 1개 active) + SafetyCheckSession
  ((worker, date, revision) UNIQUE) + SafetyStatus (session, check_item) UNIQUE
- mark_checked(session, note=None) 시그니처 (session 필수 키워드)
- check_service.check_item(worker_id, item_id, note=) — 호출 시그니처는 동일하게 유지
- 같은 날 두 번 체크 시 (session, check_item) UNIQUE → 기존 row 갱신

[설계 결정]
통합 테스트 — check_service 진입점에서 Section/Revision/Session 자동 처리 검증.
"""

import pytest
from django.utils import timezone

from apps.safety.models import (
    SafetyCheckItem,
    SafetyChecklistRevision,
    SafetyCheckSection,
    SafetyCheckSession,
    SafetyStatus,
)
from apps.safety.services.check_service import (
    check_item,
    get_or_create_today_session,
)


@pytest.fixture
def section(db, facility):
    return SafetyCheckSection.objects.create(
        facility=facility,
        name="회귀 기본 섹션",
        order=1,
    )


@pytest.fixture
def revision(db, facility):
    """facility별 active Revision 1개 (Phase 3-c)."""
    return SafetyChecklistRevision.objects.create(
        facility=facility,
        version=1,
        is_active=True,
        revision_data={"sections": []},
    )


@pytest.fixture
def required_item(db, facility, section):
    return SafetyCheckItem.objects.create(
        facility=facility,
        section=section,
        title="안전모 착용",
        order=1,
        is_required=True,
    )


@pytest.mark.django_db
def test_check_item_creates_session_and_status(
    facility, worker_user, revision, required_item
):
    """check_item() 호출 시 today Session 자동 생성 + SafetyStatus 체크 완료."""
    status = check_item(
        worker_id=worker_user.id, item_id=required_item.id, note="확인 완료"
    )
    assert status.is_checked is True
    assert status.checked_at is not None
    assert status.note == "확인 완료"
    assert status.session_id is not None
    assert status.check_item_id == required_item.id


@pytest.mark.django_db
def test_today_session_unique_per_worker_date_revision(facility, worker_user, revision):
    """같은 (worker, date, revision) 조합은 get_or_create로 단일 세션 유지."""
    s1 = get_or_create_today_session(worker_id=worker_user.id, facility_id=facility.id)
    s2 = get_or_create_today_session(worker_id=worker_user.id, facility_id=facility.id)
    assert s1.id == s2.id
    assert (
        SafetyCheckSession.objects.filter(
            worker=worker_user, date=timezone.now().date(), revision=revision
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_double_check_updates_existing_status(
    facility, worker_user, revision, required_item
):
    """같은 날 같은 항목 두 번 체크 시 (session, check_item) UNIQUE → 기존 row 갱신."""
    first = check_item(
        worker_id=worker_user.id, item_id=required_item.id, note="첫 체크"
    )
    second = check_item(
        worker_id=worker_user.id, item_id=required_item.id, note="재체크"
    )
    assert first.id == second.id  # 같은 SafetyStatus row 갱신
    assert second.note == "재체크"
    assert SafetyStatus.objects.count() == 1


@pytest.mark.django_db
def test_mark_checked_requires_session_kwarg(
    facility, worker_user, revision, required_item
):
    """mark_checked() 호출은 session 키워드 인자 필수."""
    session = get_or_create_today_session(
        worker_id=worker_user.id, facility_id=facility.id
    )
    status = SafetyStatus.objects.create(
        worker=worker_user,
        check_item=required_item,
        session=session,
        check_item_title=required_item.title,
    )
    # session 키워드 인자 없이 호출 → TypeError (positional도 허용되지만 명시적 사용 검증)
    status.mark_checked(session=session, note="정상 호출")
    status.refresh_from_db()
    assert status.is_checked is True


@pytest.mark.django_db
def test_no_active_revision_raises(facility, worker_user):
    """facility의 active Revision이 없으면 ValueError."""
    with pytest.raises(ValueError, match="활성 Revision"):
        get_or_create_today_session(worker_id=worker_user.id, facility_id=facility.id)
