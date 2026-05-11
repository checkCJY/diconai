"""
CI 정합성 테스트 — AlarmType 이넘 ↔ HazardType.type_code

Phase 2-a: HazardType seed가 fixture로 들어오므로 활성화.
한쪽만 추가/제거하면 PR 단계에서 fail → 머지 차단.
"""

from django.test import TestCase

from apps.alerts.models import HazardType
from apps.core.constants import AlarmType


class AlarmTypeConsistencyTest(TestCase):
    fixtures = ["hazard_type"]

    def test_alarm_type_enum_matches_hazard_type(self):
        db_codes = set(
            HazardType.objects.filter(is_active=True).values_list(
                "type_code", flat=True
            )
        )
        enum_codes = set(AlarmType.values)
        only_in_enum = enum_codes - db_codes
        only_in_db = db_codes - enum_codes
        self.assertFalse(
            only_in_enum or only_in_db,
            f"AlarmType ↔ HazardType 불일치:\n"
            f"  enum-only: {only_in_enum}\n"
            f"  db-only:   {only_in_db}",
        )
