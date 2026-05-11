"""
gas_facility_default ThresholdGroup 시드 (PR-G).

[목적]
phase_2_report.md §6-5 명시 — facility별 보수적 정책 도입을 위한 그룹 마스터.
실제 facility별 Threshold row는 운영자가 어드민에서 직접 입력 (운영 진입 시점).

[idempotent]
get_or_create — 운영자가 어드민에서 description 등 수정해도 마이그 재실행 시 보존.
"""

from django.db import migrations


def seed(apps, schema_editor):
    ThresholdGroup = apps.get_model("facilities", "ThresholdGroup")
    ThresholdGroup.objects.get_or_create(
        code="gas_facility_default",
        defaults={
            "name": "공장 기본 가스 임계치",
            "description": (
                "facility별 보수적 정책 그룹. evaluate_gas_risk이 facility specific 우선 후 "
                "gas_legal로 fallback. 운영자가 어드민에서 facility별 Threshold row 입력."
            ),
            "is_active": True,
        },
    )


def revert(apps, schema_editor):
    apps.get_model("facilities", "ThresholdGroup").objects.filter(
        code="gas_facility_default"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0015_threshold_facility_fk"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
