"""
Phase 3 PR3 — Session + Revision 모델 + 5단계 UNIQUE 변경 회귀 테스트.

§4-6 ⓔ: 5단계 마이그 reverse 단위 테스트는 아래 두 측면으로 보강:
  1. 모델 레벨 — Session/Revision 생성 + UNIQUE(session, check_item) 강제 + facility별 active 1개 제약
  2. 마이그 레벨 — `python manage.py migrate safety 0005` → `migrate safety` 수동 검증으로 통과 확인 (보고서 기록)
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.facilities.models import Facility
from apps.safety.models import (
    SafetyCheckItem,
    SafetyCheckSection,
    SafetyCheckSession,
    SafetyChecklistRevision,
    SafetyStatus,
)


class SessionRevisionModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.facility = Facility.objects.create(name="테스트 공장")
        cls.worker = User.objects.create_user(
            username="worker1", password="x", facility=cls.facility
        )
        cls.section = SafetyCheckSection.objects.create(
            facility=cls.facility, name="기본"
        )
        cls.item = SafetyCheckItem.objects.create(
            facility=cls.facility, section=cls.section, title="CO 농도 확인"
        )
        cls.revision = SafetyChecklistRevision.objects.create(
            facility=cls.facility,
            version=1,
            revision_data={"sections": []},
            is_active=True,
        )
        cls.session = SafetyCheckSession.objects.create(
            worker=cls.worker, date=date(2026, 5, 8), revision=cls.revision
        )

    def test_session_unique_worker_date_revision(self):
        """같은 (worker, date, revision) 중복 생성 차단"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SafetyCheckSession.objects.create(
                    worker=self.worker,
                    date=date(2026, 5, 8),
                    revision=self.revision,
                )

    def test_revision_facility_active_unique(self):
        """facility별 active Revision 1개 제약 (부분 UniqueConstraint)"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SafetyChecklistRevision.objects.create(
                    facility=self.facility,
                    version=2,
                    revision_data={"sections": []},
                    is_active=True,  # 이미 v1이 active 상태
                )

    def test_status_unique_session_item(self):
        """같은 (session, check_item) 중복 차단 — 이전 (worker, check_item) 대체"""
        SafetyStatus.objects.create(
            worker=self.worker,
            session=self.session,
            check_item=self.item,
            check_item_title=self.item.title,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SafetyStatus.objects.create(
                    worker=self.worker,
                    session=self.session,
                    check_item=self.item,
                    check_item_title=self.item.title,
                )

    def test_mark_checked_signature(self):
        """mark_checked(session, note=None) — Phase 3-c 시그니처"""
        status = SafetyStatus.objects.create(
            worker=self.worker,
            session=self.session,
            check_item=self.item,
            check_item_title=self.item.title,
        )
        status.mark_checked(session=self.session, note="확인 완료")
        status.refresh_from_db()
        self.assertTrue(status.is_checked)
        self.assertEqual(status.note, "확인 완료")
        self.assertIsNotNone(status.checked_at)
