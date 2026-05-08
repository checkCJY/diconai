"""Phase 4-g — DataRetentionPolicy 보관 배치 단위 테스트."""

from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.operations.tasks.data_retention_task import (
    is_cycle_due,
    run_data_retention,
)


class IsCycleDueTest(TestCase):
    def test_daily_always_true(self):
        self.assertTrue(is_cycle_due("daily", date(2026, 5, 8)))
        self.assertTrue(is_cycle_due("daily", date(2026, 12, 31)))

    def test_monthly_1(self):
        self.assertTrue(is_cycle_due("monthly_1", date(2026, 5, 1)))
        self.assertFalse(is_cycle_due("monthly_1", date(2026, 5, 2)))
        self.assertFalse(is_cycle_due("monthly_1", date(2026, 12, 31)))

    def test_monthly_15(self):
        self.assertTrue(is_cycle_due("monthly_15", date(2026, 5, 15)))
        self.assertFalse(is_cycle_due("monthly_15", date(2026, 5, 14)))
        self.assertFalse(is_cycle_due("monthly_15", date(2026, 5, 16)))

    def test_monthly_last(self):
        self.assertTrue(is_cycle_due("monthly_last", date(2026, 5, 31)))
        self.assertTrue(is_cycle_due("monthly_last", date(2026, 2, 28)))  # 평년
        self.assertTrue(is_cycle_due("monthly_last", date(2024, 2, 29)))  # 윤년
        self.assertFalse(is_cycle_due("monthly_last", date(2026, 5, 30)))

    def test_quarterly(self):
        # 분기 말: 3/31, 6/30, 9/30, 12/31
        self.assertTrue(is_cycle_due("quarterly", date(2026, 3, 31)))
        self.assertTrue(is_cycle_due("quarterly", date(2026, 6, 30)))
        self.assertTrue(is_cycle_due("quarterly", date(2026, 9, 30)))
        self.assertTrue(is_cycle_due("quarterly", date(2026, 12, 31)))
        self.assertFalse(is_cycle_due("quarterly", date(2026, 5, 31)))  # 분기말 아님
        self.assertFalse(is_cycle_due("quarterly", date(2026, 3, 30)))  # 31일 아님

    def test_unknown_cycle_returns_false(self):
        self.assertFalse(is_cycle_due("invalid", date(2026, 5, 8)))


class RunDataRetentionTest(TestCase):
    def setUp(self):
        # PR-C 마이그 시드(5종 기본 정책) 제거 — 본 테스트는 정책을 직접 만들어 검증
        from apps.operations.models import DataRetentionPolicy

        DataRetentionPolicy.objects.all().delete()

    def test_no_active_policy_returns_empty(self):
        """활성 정책 없음 → 빈 dict"""
        result = run_data_retention(dry_run=True)
        self.assertEqual(result, {})

    def test_dry_run_does_not_delete(self):
        """dry_run=True 시 실제 삭제 없음 — 카운트만 반환"""
        from apps.facilities.models import Facility, GasSensor
        from apps.monitoring.models import GasData
        from apps.operations.models import DataRetentionPolicy

        facility = Facility.objects.create(name="test")
        sensor = GasSensor.objects.create(
            facility=facility, device_id="GS-X", device_name="test", x=0, y=0
        )
        # 100일 전 정상 row 1개
        old_at = timezone.now() - timedelta(days=100)
        GasData.objects.create(
            gas_sensor=sensor, co=5, measured_at=old_at, max_risk_level="normal"
        )
        DataRetentionPolicy.objects.create(
            device_type="gas_sensor",
            data_category="gas_raw",
            raw_retention_days=30,
            history_retention_days=90,
            delete_cycle="daily",
        )

        result = run_data_retention(dry_run=True)

        # 1개 후보, 실제 row는 그대로
        self.assertEqual(sum(result.values()), 1)
        self.assertEqual(GasData.objects.count(), 1)

    def test_actual_run_deletes_old_rows(self):
        """dry_run=False 시 실제 삭제 — 보관 기간 초과 row 제거"""
        from apps.facilities.models import Facility, GasSensor
        from apps.monitoring.models import GasData
        from apps.operations.models import DataRetentionPolicy

        facility = Facility.objects.create(name="test")
        sensor = GasSensor.objects.create(
            facility=facility, device_id="GS-Y", device_name="test", x=0, y=0
        )
        old_at = timezone.now() - timedelta(days=100)
        recent_at = timezone.now() - timedelta(days=10)
        GasData.objects.create(
            gas_sensor=sensor, co=5, measured_at=old_at, max_risk_level="normal"
        )
        GasData.objects.create(
            gas_sensor=sensor, co=5, measured_at=recent_at, max_risk_level="normal"
        )
        DataRetentionPolicy.objects.create(
            device_type="gas_sensor",
            data_category="gas_raw",
            raw_retention_days=30,
            history_retention_days=90,
            delete_cycle="daily",
        )

        result = run_data_retention(dry_run=False)

        # 100일 전 1개만 삭제, 10일 전 1개는 보존
        self.assertEqual(sum(result.values()), 1)
        self.assertEqual(GasData.objects.count(), 1)
        self.assertEqual(GasData.objects.first().measured_at.date(), recent_at.date())

    def test_skip_when_cycle_not_due(self):
        """delete_cycle이 today에 해당 안 함 → 스킵"""
        from apps.operations.models import DataRetentionPolicy

        DataRetentionPolicy.objects.create(
            device_type="gas_sensor",
            data_category="gas_raw",
            raw_retention_days=30,
            history_retention_days=90,
            delete_cycle="quarterly",  # 분기 말만
        )
        # 오늘이 분기 말 아니라고 강제
        with patch(
            "apps.operations.tasks.data_retention_task.timezone.now"
        ) as mock_now:
            from datetime import datetime, timezone as tz_mod

            mock_now.return_value = datetime(2026, 5, 8, tzinfo=tz_mod.utc)
            result = run_data_retention(dry_run=True)

        self.assertEqual(result, {})  # 정책 0건 실행
