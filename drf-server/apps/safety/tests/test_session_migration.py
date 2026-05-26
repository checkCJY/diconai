"""
Phase 3 PR3 — Session + Revision 모델 + 5단계 UNIQUE 변경 회귀 테스트.

§4-6 ⓔ: 5단계 마이그 reverse 단위 테스트는 아래 두 측면으로 보강:
  1. 모델 레벨 — Session/Revision 생성 + UNIQUE(session, check_item) 강제 + facility별 active 1개 제약
  2. 마이그 레벨 — `python manage.py migrate safety 0005` → `migrate safety` 수동 검증으로 통과 확인 (보고서 기록)
"""

# 이성현 수정 — Django TestCase.setUpTestData → pytest fixture로 전환 (PG 시퀀스 충돌 방지)
# setUpTestData는 클래스 단위 트랜잭션을 사용하여 pytest-django의 reset_sequences
# autouse 픽스처와 실행 순서 충돌이 발생함.
# pytest fixture로 전환 후 함수 단위 savepoint 격리로 동일 보장.

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.facilities.models import Facility
from apps.safety.models import (
    SafetyCheckItem,
    SafetyCheckSection,
    SafetyCheckSession,
    SafetyChecklistRevision,
    SafetyStatus,
)


@pytest.fixture
def sess_facility(db):
    """이성현 추가 — 세션 마이그레이션 테스트용 공장 (conftest facility와 독립)."""
    return Facility.objects.create(name="테스트 공장")


@pytest.fixture
def sess_worker(db, sess_facility):
    """이성현 추가 — 세션 마이그레이션 테스트용 작업자."""
    User = get_user_model()
    return User.objects.create_user(
        username="worker1", password="x", facility=sess_facility
    )


@pytest.fixture
def sess_section(db, sess_facility):
    return SafetyCheckSection.objects.create(facility=sess_facility, name="기본")


@pytest.fixture
def sess_item(db, sess_facility, sess_section):
    return SafetyCheckItem.objects.create(
        facility=sess_facility, section=sess_section, title="CO 농도 확인"
    )


@pytest.fixture
def sess_revision(db, sess_facility):
    return SafetyChecklistRevision.objects.create(
        facility=sess_facility,
        version=1,
        revision_data={"sections": []},
        is_active=True,
    )


@pytest.fixture
def sess_session(db, sess_worker, sess_revision):
    return SafetyCheckSession.objects.create(
        worker=sess_worker, date=date(2026, 5, 8), revision=sess_revision
    )


@pytest.mark.django_db
def test_session_unique_worker_date_revision(sess_worker, sess_revision, sess_session):
    """같은 (worker, date, revision) 중복 생성 차단"""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SafetyCheckSession.objects.create(
                worker=sess_worker,
                date=date(2026, 5, 8),
                revision=sess_revision,
            )


@pytest.mark.django_db
def test_revision_facility_active_unique(sess_facility, sess_revision):
    """facility별 active Revision 1개 제약 (부분 UniqueConstraint)"""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SafetyChecklistRevision.objects.create(
                facility=sess_facility,
                version=2,
                revision_data={"sections": []},
                is_active=True,  # 이미 v1이 active 상태
            )


@pytest.mark.django_db
def test_status_unique_session_item(sess_worker, sess_session, sess_item):
    """같은 (session, check_item) 중복 차단 — 이전 (worker, check_item) 대체"""
    SafetyStatus.objects.create(
        worker=sess_worker,
        session=sess_session,
        check_item=sess_item,
        check_item_title=sess_item.title,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SafetyStatus.objects.create(
                worker=sess_worker,
                session=sess_session,
                check_item=sess_item,
                check_item_title=sess_item.title,
            )


@pytest.mark.django_db
def test_mark_checked_signature(sess_worker, sess_session, sess_item):
    """mark_checked(session, note=None) — Phase 3-c 시그니처"""
    status = SafetyStatus.objects.create(
        worker=sess_worker,
        session=sess_session,
        check_item=sess_item,
        check_item_title=sess_item.title,
    )
    status.mark_checked(session=sess_session, note="확인 완료")
    status.refresh_from_db()
    assert status.is_checked is True
    assert status.note == "확인 완료"
    assert status.checked_at is not None
