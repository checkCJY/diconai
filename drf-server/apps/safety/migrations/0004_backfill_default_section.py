"""
3b 마이그 2단계 — facility별 "기본" Section 자동 생성 + 기존 Item 일괄 백필.

forward:
  facility별 SafetyCheckItem이 1개 이상 있고 section=NULL인 row가 있으면
  해당 facility에 "기본" Section을 get_or_create한 뒤 모든 Item.section을 그쪽으로 채움.

reverse:
  본 마이그에서 생성한 "기본" Section의 Item.section을 NULL로 되돌림.
  Section 자체는 다른 마이그에서 추가됐을 가능성이 있으니 자동 삭제하지 않음.
"""

from django.db import migrations


def create_default_sections_and_backfill(apps, schema_editor):
    Facility = apps.get_model("facilities", "Facility")
    SafetyCheckSection = apps.get_model("safety", "SafetyCheckSection")
    SafetyCheckItem = apps.get_model("safety", "SafetyCheckItem")

    # facility별로 section=NULL인 Item이 있는 facility만 처리
    facility_ids_with_null_items = (
        SafetyCheckItem.objects.filter(section__isnull=True)
        .values_list("facility_id", flat=True)
        .distinct()
    )

    for facility_id in facility_ids_with_null_items:
        if not Facility.objects.filter(pk=facility_id).exists():
            continue
        section, _ = SafetyCheckSection.objects.get_or_create(
            facility_id=facility_id,
            name="기본",
            defaults={
                "description": "마이그레이션 시 자동 생성된 기본 섹션 (Phase 3-b 백필)",
                "order": 0,
                "is_active": True,
            },
        )
        SafetyCheckItem.objects.filter(
            facility_id=facility_id, section__isnull=True
        ).update(section=section)


def revert_default_sections_and_backfill(apps, schema_editor):
    SafetyCheckSection = apps.get_model("safety", "SafetyCheckSection")
    SafetyCheckItem = apps.get_model("safety", "SafetyCheckItem")

    default_sections = SafetyCheckSection.objects.filter(name="기본")
    SafetyCheckItem.objects.filter(section__in=default_sections).update(section=None)


class Migration(migrations.Migration):
    dependencies = [
        ("safety", "0003_safetychecksection_safetycheckitem_section_and_more"),
    ]

    operations = [
        migrations.RunPython(
            create_default_sections_and_backfill,
            revert_default_sections_and_backfill,
        ),
    ]
