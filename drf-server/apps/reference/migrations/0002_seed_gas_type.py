"""
GAS_TYPE CodeGroup + CommonCode 10종 시드 (LEL 포함 — PR-E에서 별도 제거 예정).

[2026-05-09 PR-A 회귀 점검 후속]
원본은 call_command("loaddata", "gas_type") 호출이었으나, 동일 위험으로 historical apps 패턴
재작성. fixture json은 보존 (수동 loaddata + 어드민 import 용).

운영 DB는 이미 0002 적용 완료라 본 변경 영향 없음.
"""

from django.db import migrations

GAS_TYPES = [
    {"pk": 1, "code": "co", "name": "CO (일산화탄소)", "sort_order": 1},
    {"pk": 2, "code": "h2s", "name": "H2S (황화수소)", "sort_order": 2},
    {"pk": 3, "code": "co2", "name": "CO2 (이산화탄소)", "sort_order": 3},
    {"pk": 4, "code": "o2", "name": "O2 (산소)", "sort_order": 4},
    {"pk": 5, "code": "no2", "name": "NO2 (이산화질소)", "sort_order": 5},
    {"pk": 6, "code": "so2", "name": "SO2 (이산화황)", "sort_order": 6},
    {"pk": 7, "code": "o3", "name": "O3 (오존)", "sort_order": 7},
    {"pk": 8, "code": "nh3", "name": "NH3 (암모니아)", "sort_order": 8},
    {"pk": 9, "code": "voc", "name": "VOC (휘발성유기화합물)", "sort_order": 9},
    {"pk": 10, "code": "lel", "name": "LEL (폭발하한계)", "sort_order": 10},
]


def seed(apps, schema_editor):
    CodeGroup = apps.get_model("reference", "CodeGroup")
    CommonCode = apps.get_model("reference", "CommonCode")

    CodeGroup.objects.update_or_create(
        pk=1,
        defaults={
            "code": "GAS_TYPE",
            "name": "가스 종류",
            "description": "유해가스 9종 + LEL — GasTypeChoices 이넘과 1:1",
            "is_active": True,
        },
    )

    for c in GAS_TYPES:
        CommonCode.objects.update_or_create(
            pk=c["pk"],
            defaults={
                "group_id": 1,
                "code": c["code"],
                "name": c["name"],
                "sort_order": c["sort_order"],
                "is_active": True,
            },
        )


def revert(apps, schema_editor):
    CommonCode = apps.get_model("reference", "CommonCode")
    CodeGroup = apps.get_model("reference", "CodeGroup")
    CommonCode.objects.filter(group__code="GAS_TYPE").delete()
    CodeGroup.objects.filter(code="GAS_TYPE").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reference", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
