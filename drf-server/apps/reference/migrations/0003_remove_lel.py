"""
LEL dead code 제거 (PR-E).

센서 정의서(2026-04-01) 9종에 LEL 미포함. GasTypeChoices에서 LEL 제거됨에 따라
DB의 CommonCode(group=GAS_TYPE, code=lel) row도 정리.

[운영 DB 영향]
0002에서 LEL row가 시드된 운영 DB는 본 마이그가 LEL row를 delete. 새 환경 fresh migrate
는 0002에서 이미 LEL 제외 (PR-E 갱신) — 본 마이그는 noop.

[reverse]
LEL 복원이 필요할 경우 fixture/모델 정의도 함께 복원해야 의미 있음. 본 마이그 reverse는
LEL row 재생성으로만 (이전 상태 복원).
"""

from django.db import migrations


def remove_lel(apps, schema_editor):
    CommonCode = apps.get_model("reference", "CommonCode")
    CommonCode.objects.filter(group__code="GAS_TYPE", code="lel").delete()


def restore_lel(apps, schema_editor):
    CommonCode = apps.get_model("reference", "CommonCode")
    CodeGroup = apps.get_model("reference", "CodeGroup")
    group = CodeGroup.objects.filter(code="GAS_TYPE").first()
    if group is None:
        return
    CommonCode.objects.update_or_create(
        pk=10,
        defaults={
            "group": group,
            "code": "lel",
            "name": "LEL (폭발하한계)",
            "sort_order": 10,
            "is_active": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("reference", "0002_seed_gas_type"),
    ]

    operations = [
        migrations.RunPython(remove_lel, restore_lel),
    ]
