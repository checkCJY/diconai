"""
CI 정합성 테스트 — RiskLevel 이넘 ↔ RiskLevelStandard.code

Phase 1: fixture로 row 3개(normal/warning/danger) 시드.
어드민 readonly_fields = ['code']와 함께 이중 잠금.
"""

from django.test import TestCase

from apps.core.constants import RiskLevel
from apps.core.models import RiskLevelStandard


class RiskLevelStandardConsistencyTest(TestCase):
    fixtures = ["risk_level_standard"]

    def test_enum_matches_db(self):
        db_codes = set(RiskLevelStandard.objects.values_list("code", flat=True))
        enum_codes = set(RiskLevel.values)
        only_in_enum = enum_codes - db_codes
        only_in_db = db_codes - enum_codes
        self.assertFalse(
            only_in_enum or only_in_db,
            f"RiskLevel ↔ RiskLevelStandard 불일치:\n"
            f"  enum-only: {only_in_enum}\n"
            f"  db-only:   {only_in_db}",
        )

    def test_priority_unique(self):
        priorities = list(
            RiskLevelStandard.objects.values_list("event_priority", flat=True)
        )
        self.assertEqual(
            len(priorities),
            len(set(priorities)),
            f"event_priority 중복: {priorities}",
        )
