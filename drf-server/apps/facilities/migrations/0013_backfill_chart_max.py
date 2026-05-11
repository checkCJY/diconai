"""
Threshold.chart_max 백필 마이그 (Phase 1~4 회귀 점검 fix).

power_default 그룹의 power_w 항목에 chart_max=3500 채움.
이전 core/constants.POWER_THRESHOLDS["maxY"] 값 (Phase A 기준)을 DB로 이전.

reverse 시 chart_max=NULL로 복원 (forward와 대칭).
"""

from decimal import Decimal

from django.db import migrations


def backfill_chart_max(apps, schema_editor):
    Threshold = apps.get_model("facilities", "Threshold")
    Threshold.objects.filter(
        group__code="power_default", measurement_item="power_w"
    ).update(chart_max=Decimal("3500"))


def reverse_backfill_chart_max(apps, schema_editor):
    Threshold = apps.get_model("facilities", "Threshold")
    Threshold.objects.filter(
        group__code="power_default", measurement_item="power_w"
    ).update(chart_max=None)


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0012_threshold_chart_max"),
    ]

    operations = [
        migrations.RunPython(backfill_chart_max, reverse_backfill_chart_max),
    ]
