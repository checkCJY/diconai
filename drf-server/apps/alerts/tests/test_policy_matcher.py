"""Phase 4-e — policy_matcher 단위 테스트."""

from django.test import TestCase

from apps.alerts.models import AlertPolicy
from apps.alerts.services.policy_matcher import (
    compute_condition_summary,
    match_policy,
    save_policy,
)
from apps.core.constants import AlarmType
from apps.facilities.models import Facility


class PolicyMatcherTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.facility_a = Facility.objects.create(name="공장 A")
        cls.facility_b = Facility.objects.create(name="공장 B")

    def test_match_specific_facility(self):
        """target_facility 일치 정책 매칭"""
        policy = AlertPolicy.objects.create(
            name="A 가스",
            event_type=AlarmType.GAS_THRESHOLD,
            target_facility=self.facility_a,
            target_user_types=["facility_admin"],
            channels=["popup"],
        )
        match = match_policy(
            event_type=AlarmType.GAS_THRESHOLD, facility_id=self.facility_a.id
        )
        self.assertEqual(match, policy)

    def test_match_global_policy_when_facility_specific_absent(self):
        """전사 정책 (target_facility=NULL) fallback"""
        global_policy = AlertPolicy.objects.create(
            name="전사 가스",
            event_type=AlarmType.GAS_THRESHOLD,
            target_facility=None,
            target_user_types=["super_admin"],
            channels=["popup"],
        )
        match = match_policy(
            event_type=AlarmType.GAS_THRESHOLD, facility_id=self.facility_a.id
        )
        self.assertEqual(match, global_policy)

    def test_match_specific_takes_priority_over_global(self):
        """특정 facility 정책이 전사 정책보다 우선"""
        AlertPolicy.objects.create(
            name="전사",
            event_type=AlarmType.GAS_THRESHOLD,
            target_facility=None,
            target_user_types=["super_admin"],
            channels=["popup"],
        )
        specific = AlertPolicy.objects.create(
            name="A 공장 전용",
            event_type=AlarmType.GAS_THRESHOLD,
            target_facility=self.facility_a,
            target_user_types=["facility_admin"],
            channels=["popup"],
        )
        match = match_policy(
            event_type=AlarmType.GAS_THRESHOLD, facility_id=self.facility_a.id
        )
        self.assertEqual(match, specific)

    def test_no_match_returns_none(self):
        """일치하는 정책 없음 → None"""
        AlertPolicy.objects.create(
            name="B 가스",
            event_type=AlarmType.GAS_THRESHOLD,
            target_facility=self.facility_b,
            target_user_types=["facility_admin"],
            channels=["popup"],
        )
        match = match_policy(
            event_type=AlarmType.GAS_THRESHOLD, facility_id=self.facility_a.id
        )
        self.assertIsNone(match)

    def test_save_policy_updates_condition_summary(self):
        """save_policy() 호출 시 condition_summary 자동 갱신"""
        policy = AlertPolicy(
            name="테스트",
            event_type=AlarmType.PPE_VIOLATION,
            target_facility=self.facility_a,
            target_user_types=["worker"],
            channels=["popup", "sms"],
        )
        save_policy(policy)
        self.assertIn("PPE 미착용", policy.condition_summary)
        self.assertIn("공장 A", policy.condition_summary)
        self.assertIn("popup, sms", policy.condition_summary)

    def test_compute_condition_summary_global(self):
        """전사 정책 condition_summary는 '전사' 포함"""
        policy = AlertPolicy(
            name="전사 PPE",
            event_type=AlarmType.PPE_VIOLATION,
            target_facility=None,
            target_user_types=["worker"],
            channels=["popup"],
        )
        summary = compute_condition_summary(policy)
        self.assertIn("전사", summary)
