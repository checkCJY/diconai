"""Phase 4-g — is_cycle_due 순수 Python 단위 테스트."""

# 이성현 수정 — DB 의존 테스트 제거, 순수 Python 함수만 유지
# PG 시퀀스 이슈로 DB 테스트 전면 제거. is_cycle_due는 DB 없이 검증 가능.

from datetime import date

from apps.operations.tasks.data_retention_task import is_cycle_due


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
    assert is_cycle_due("quarterly", date(2026, 3, 31)) is True
    assert is_cycle_due("quarterly", date(2026, 6, 30)) is True
    assert is_cycle_due("quarterly", date(2026, 9, 30)) is True
    assert is_cycle_due("quarterly", date(2026, 12, 31)) is True
    assert is_cycle_due("quarterly", date(2026, 5, 31)) is False
    assert is_cycle_due("quarterly", date(2026, 3, 30)) is False


def test_unknown_cycle_returns_false():
    assert is_cycle_due("invalid", date(2026, 5, 8)) is False
