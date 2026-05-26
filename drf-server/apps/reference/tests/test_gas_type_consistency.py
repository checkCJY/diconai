"""
CI 정합성 테스트 — GasTypeChoices 이넘 ↔ CommonCode(GAS_TYPE)

Phase 1: GAS_TYPE 그룹이 fixture로 시드되므로 이 테스트는 즉시 활성화 가능.
한쪽만 추가/제거하면 PR 단계에서 fail → 머지 차단.
"""

# 이성현 수정 — Django TestCase(fixtures=[]) → pytest 스타일로 전환 (PG 시퀀스 충돌 방지)
# TestCase.fixtures = ["gas_type"]를 pytest fixture로 대체.
# call_command("loaddata")는 테스트 savepoint 내에서 실행되어 테스트 종료 시 자동 롤백됨.

import pytest

from apps.core.constants import GasTypeChoices
from apps.reference.models import CodeGroup


@pytest.fixture
def gas_type_fixture(db):
    """이성현 추가 — gas_type JSON 픽스처 로드 (TestCase.fixtures = ["gas_type"] 대체)."""
    from django.core.management import call_command

    call_command("loaddata", "gas_type", verbosity=0)


@pytest.mark.django_db
def test_gas_type_enum_matches_common_code(gas_type_fixture):
    try:
        group = CodeGroup.objects.get(code="GAS_TYPE")
    except CodeGroup.DoesNotExist:
        pytest.fail(
            "CodeGroup(GAS_TYPE)이 시드되지 않았습니다. "
            "apps/reference/fixtures/gas_type.json 또는 마이그레이션 확인."
        )
    db_codes = set(group.codes.filter(is_active=True).values_list("code", flat=True))
    enum_codes = set(GasTypeChoices.values)
    only_in_enum = enum_codes - db_codes
    only_in_db = db_codes - enum_codes
    assert not (only_in_enum or only_in_db), (
        f"GasTypeChoices ↔ CommonCode(GAS_TYPE) 불일치:\n"
        f"  enum-only: {only_in_enum}\n"
        f"  db-only:   {only_in_db}"
    )
