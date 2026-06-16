"""
power_facility_default ThresholdGroup + 3축(W·A·V) 임계치 시드 (전력 Phase 1).

[목적]
power-threshold-roadmap.md §1단계 — 정격 % 기반 임계치 마스터.
evaluate_power_risk()이 power_facility_default 우선 조회 후 없으면 power_default
절대값으로 fallback. 가스의 gas_legal ↔ gas_facility_default 우선순위 패턴 재사용.

[시드 내용]
- power_w: 정격 80%/100% (warning/danger, 단방향)
- current: 정격 80%/100% (warning/danger, 단방향)
- voltage: 정격 ±5% warning / ±10% danger (양방향 — 저전압도 위험)

[idempotent]
update_or_create — 운영자가 어드민에서 임계치 수정해도 마이그 재실행 시 보존.

[기존 데이터 보호]
power_default.power_w (2200/2860W 절대값)은 미변경. evaluate_power_risk()이
정격 정보 없을 때 절대값 fallback으로 사용.
"""

from decimal import Decimal

from django.db import migrations


def seed(apps, schema_editor):
    ThresholdGroup = apps.get_model("facilities", "ThresholdGroup")
    Threshold = apps.get_model("facilities", "Threshold")

    group, _ = ThresholdGroup.objects.update_or_create(
        code="power_facility_default",
        defaults={
            "name": "전력 정격 기반 임계치",
            "description": (
                "PowerDevice.channel_meta[ch][rated_*]에 대한 % 기반 임계치. "
                "evaluate_power_risk이 이 그룹 우선 후 power_default로 fallback."
            ),
            "is_active": True,
        },
    )

    Threshold.objects.update_or_create(
        group=group,
        measurement_item="power_w",
        facility=None,
        defaults={
            "warning_max": Decimal("80"),
            "danger_max": Decimal("100"),
            "unit": "%",
            "description": "전력 W 정격 대비 (warning 80%, danger 100%)",
            "is_active": True,
        },
    )
    Threshold.objects.update_or_create(
        group=group,
        measurement_item="current",
        facility=None,
        defaults={
            "warning_max": Decimal("80"),
            "danger_max": Decimal("100"),
            "unit": "%",
            "description": "전류 A 정격 대비 (warning 80%, danger 100%)",
            "is_active": True,
        },
    )
    Threshold.objects.update_or_create(
        group=group,
        measurement_item="voltage",
        facility=None,
        defaults={
            "warning_min": Decimal("95"),
            "warning_max": Decimal("105"),
            "danger_min": Decimal("90"),
            "danger_max": Decimal("110"),
            "unit": "%",
            "description": "전압 V 정격 대비 양방향 (warning ±5%, danger ±10%)",
            "is_active": True,
        },
    )


def revert(apps, schema_editor):
    Threshold = apps.get_model("facilities", "Threshold")
    ThresholdGroup = apps.get_model("facilities", "ThresholdGroup")
    Threshold.objects.filter(group__code="power_facility_default").delete()
    ThresholdGroup.objects.filter(code="power_facility_default").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0017_seed_power_channel_meta"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
