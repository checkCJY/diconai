"""Phase 4-g — DataRetentionPolicy 보관 배치 단위 테스트."""

# 이성현 수정 — Django TestCase → pytest 스타일로 전환 (PG 시퀀스 충돌 방지)
# TestCase는 pytest-django의 django_db_setup 경로를 우회해 conftest의
# reset_sequences autouse 픽스처가 적용되지 않는 경우가 있었음.
# pytest 스타일 전환 후 동일 경로를 거쳐 PG 시퀀스 리셋이 보장됨.

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.operations.tasks.data_retention_task import (
    is_cycle_due,
    run_data_retention,
)


@pytest.fixture
def clean_policies(db):
    """이성현 추가 — PR-C 마이그 시드(5종 기본 정책) 제거, 테스트별 정책 직접 생성."""
    from apps.operations.models import DataRetentionPolicy

    DataRetentionPolicy.objects.all().delete()


# ── is_cycle_due 단위 테스트 (DB 불필요) ──────────────────────────────────────


def test_daily_always_true():
    assert is_cycle_due("daily", date(2026, 5, 8)) is True
    assert is_cycle_due("daily", date(2026, 12, 31)) is True


def test_monthly_1():
    assert is_cycle_due("monthly_1", date(2026, 5, 1)) is True
    assert is_cycle_due("monthly_1", date(2026, 5, 2)) is False
    assert is_cycle_due("monthly_1", date(2026, 12, 31)) is False


def test_monthly_15():
    assert is_cycle_due("monthly_15", date(2026, 5, 15)) is True
    assert is_cycle_due("monthly_15", date(2026, 5, 14)) is False
    assert is_cycle_due("monthly_15", date(2026, 5, 16)) is False


def test_monthly_last():
    assert is_cycle_due("monthly_last", date(2026, 5, 31)) is True
    assert is_cycle_due("monthly_last", date(2026, 2, 28)) is True  # 평년
    assert is_cycle_due("monthly_last", date(2024, 2, 29)) is True  # 윤년
    assert is_cycle_due("monthly_last", date(2026, 5, 30)) is False


def test_quarterly():
    # 분기 말: 3/31, 6/30, 9/30, 12/31
    assert is_cycle_due("quarterly", date(2026, 3, 31)) is True
    assert is_cycle_due("quarterly", date(2026, 6, 30)) is True
    assert is_cycle_due("quarterly", date(2026, 9, 30)) is True
    assert is_cycle_due("quarterly", date(2026, 12, 31)) is True
    assert is_cycle_due("quarterly", date(2026, 5, 31)) is False  # 분기말 아님
    assert is_cycle_due("quarterly", date(2026, 3, 30)) is False  # 31일 아님


def test_unknown_cycle_returns_false():
    assert is_cycle_due("invalid", date(2026, 5, 8)) is False


# ── run_data_retention 통합 테스트 (DB 필요) ──────────────────────────────────


@pytest.mark.django_db
def test_no_active_policy_returns_empty(clean_policies):
    """활성 정책 없음 → 빈 dict"""
    result = run_data_retention(dry_run=True)
    assert result == {}


@pytest.mark.django_db
def test_dry_run_does_not_delete(clean_policies):
    """dry_run=True 시 실제 삭제 없음 — 카운트만 반환"""
    from apps.facilities.models import Facility, GasSensor
    from apps.monitoring.models import GasData
    from apps.operations.models import DataRetentionPolicy

    facility = Facility.objects.create(name="test")
    sensor = GasSensor.objects.create(
        facility=facility, device_id="GS-X", device_name="test", x=0, y=0
    )
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
    assert sum(result.values()) == 1
    assert GasData.objects.count() == 1


@pytest.mark.django_db
def test_actual_run_deletes_old_rows(clean_policies):
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
    assert sum(result.values()) == 1
    assert GasData.objects.count() == 1
    assert GasData.objects.first().measured_at.date() == recent_at.date()


@pytest.mark.django_db
def test_skip_when_cycle_not_due(clean_policies):
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
    with patch("apps.operations.tasks.data_retention_task.timezone.now") as mock_now:
        from datetime import datetime, timezone as tz_mod

        mock_now.return_value = datetime(2026, 5, 8, tzinfo=tz_mod.utc)
        result = run_data_retention(dry_run=True)

    assert result == {}  # 정책 0건 실행
