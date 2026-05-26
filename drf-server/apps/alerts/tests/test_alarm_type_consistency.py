"""
CI 정합성 테스트 — AlarmType 이넘 ↔ HazardType.type_code

Phase 2-a: HazardType seed가 fixture로 들어오므로 활성화.
한쪽만 추가/제거하면 PR 단계에서 fail → 머지 차단.
"""

# 이성현 수정 — Django TestCase → pytest 스타일로 전환 (PG 시퀀스 충돌 방지)
# TestCase.fixtures = ["hazard_type"]를 pytest fixture로 대체.
# test_gas_type_consistency.py와 동일 패턴.

import pytest

from apps.alerts.models import HazardType
from apps.core.constants import AlarmType


@pytest.fixture
def hazard_type_fixture(db):
    """이성현 추가 — hazard_type JSON 픽스처 로드 (TestCase.fixtures = ["hazard_type"] 대체)."""
    from django.core.management import call_command

    call_command("loaddata", "hazard_type", verbosity=0)


@pytest.mark.django_db
def test_alarm_type_enum_matches_hazard_type(hazard_type_fixture):
    db_codes = set(
        HazardType.objects.filter(is_active=True).values_list("type_code", flat=True)
    )
    enum_codes = set(AlarmType.values)
    only_in_enum = enum_codes - db_codes
    only_in_db = db_codes - enum_codes
    assert not (only_in_enum or only_in_db), (
        f"AlarmType ↔ HazardType 불일치:\n"
        f"  enum-only: {only_in_enum}\n"
        f"  db-only:   {only_in_db}"
    )
