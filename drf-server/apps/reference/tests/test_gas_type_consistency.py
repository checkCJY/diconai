"""
CI 정합성 테스트 — GasTypeChoices 이넘 ↔ CommonCode(GAS_TYPE)

Phase 1: GAS_TYPE 그룹이 fixture로 시드되므로 이 테스트는 즉시 활성화 가능.
한쪽만 추가/제거하면 PR 단계에서 fail → 머지 차단.
"""

from django.test import TestCase

from apps.core.constants import GasTypeChoices
from apps.reference.models import CodeGroup


class GasTypeConsistencyTest(TestCase):
    fixtures = ["gas_type"]

    def test_gas_type_enum_matches_common_code(self):
        """GasTypeChoices 이넘 코드와 CommonCode(GAS_TYPE) 활성 코드 집합 일치 확인."""
        try:
            group = CodeGroup.objects.get(code="GAS_TYPE")
        except CodeGroup.DoesNotExist:
            self.fail(
                "CodeGroup(GAS_TYPE)이 시드되지 않았습니다. "
                "apps/reference/fixtures/gas_type.json 또는 마이그레이션 확인."
            )
        db_codes = set(
            group.codes.filter(is_active=True).values_list("code", flat=True)
        )
        enum_codes = set(GasTypeChoices.values)
        only_in_enum = enum_codes - db_codes
        only_in_db = db_codes - enum_codes
        self.assertFalse(
            only_in_enum or only_in_db,
            f"GasTypeChoices ↔ CommonCode(GAS_TYPE) 불일치:\n"
            f"  enum-only: {only_in_enum}\n"
            f"  db-only:   {only_in_db}",
        )
