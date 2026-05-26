"""
CI 정합성 테스트 — RiskLevel 이넘 ↔ RiskLevelStandard.code

Phase 1: fixture로 row 3개(normal/warning/danger) 시드.
어드민 readonly_fields = ['code']와 함께 이중 잠금.
"""

# 이성현 수정 — Django TestCase → pytest 스타일로 전환 (PG 시퀀스 충돌 방지)
# TestCase.fixtures = ["risk_level_standard"]를 pytest fixture로 대체.

import pytest

from apps.core.constants import RiskLevel
from apps.core.models import RiskLevelStandard


@pytest.fixture
def risk_level_fixture(db):
    """이성현 추가 — risk_level_standard JSON 픽스처 로드."""
    from django.core.management import call_command

    call_command("loaddata", "risk_level_standard", verbosity=0)


@pytest.mark.django_db
def test_enum_matches_db(risk_level_fixture):
    db_codes = set(RiskLevelStandard.objects.values_list("code", flat=True))
    enum_codes = set(RiskLevel.values)
    only_in_enum = enum_codes - db_codes
    only_in_db = db_codes - enum_codes
    assert not (only_in_enum or only_in_db), (
        f"RiskLevel ↔ RiskLevelStandard 불일치:\n"
        f"  enum-only: {only_in_enum}\n"
        f"  db-only:   {only_in_db}"
    )


@pytest.mark.django_db
def test_priority_unique(risk_level_fixture):
    priorities = list(
        RiskLevelStandard.objects.values_list("event_priority", flat=True)
    )
    assert len(priorities) == len(set(priorities)), f"event_priority 중복: {priorities}"
