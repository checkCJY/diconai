"""
Phase 4-d — Threshold default seed (gas_legal + power_default).

이전 core/constants.py POWER_THRESHOLDS + facilities LEGAL_THRESHOLDS 상수에서
fixture로 이전. 가스 9종(co/h2s/co2/o2/no2/so2/o3/nh3/voc) + 전력 1종(power_w).
"""

from django.core.management import call_command
from django.db import migrations


def load_fixture(apps, schema_editor):
    call_command("loaddata", "threshold_default", app_label="facilities")


def revert_fixture(apps, schema_editor):
    apps.get_model("facilities", "Threshold").objects.filter(
        group__code__in=["gas_legal", "power_default"]
    ).delete()
    apps.get_model("facilities", "ThresholdGroup").objects.filter(
        code__in=["gas_legal", "power_default"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0010_thresholdgroup_threshold"),
    ]

    operations = [
        migrations.RunPython(load_fixture, revert_fixture),
    ]
