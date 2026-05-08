"""
Phase 4-d — Threshold default seed (gas_legal + power_default).

이전 core/constants.py POWER_THRESHOLDS + facilities LEGAL_THRESHOLDS 상수에서
fixture로 이전. 가스 9종(co/h2s/co2/o2/no2/so2/o3/nh3/voc) + 전력 1종(power_w).

[2026-05-08 회귀 점검 fix]
원본은 call_command("loaddata", "threshold_default") 호출이었으나, fixture는 이후
마이그(0012_threshold_chart_max)에서 추가된 chart_max 필드를 미리 알 수 없어 새 환경
fresh migrate 시점에 실패. historical apps.get_model 기반 explicit create로 재작성.

운영 DB는 이미 0011 적용 완료라 본 변경 영향 없음 (forward만 새 환경에서 실행).
"""

from decimal import Decimal

from django.db import migrations

THRESHOLD_GROUPS = [
    {
        "pk": 1,
        "code": "gas_legal",
        "name": "가스 법정 기준",
        "description": "산업안전보건법 기준 가스 임계치 (정휘훈 plan #3)",
    },
    {
        "pk": 2,
        "code": "power_default",
        "name": "전력 기본 임계치",
        "description": "POWER_THRESHOLDS 상수에서 이전 (Phase 4)",
    },
]

THRESHOLDS = [
    {
        "pk": 1,
        "group_pk": 1,
        "measurement_item": "co",
        "warning_max": "25",
        "danger_max": "200",
        "unit": "ppm",
        "description": "CO (일산화탄소)",
    },
    {
        "pk": 2,
        "group_pk": 1,
        "measurement_item": "h2s",
        "warning_max": "10",
        "danger_max": "15",
        "unit": "ppm",
        "description": "H2S (황화수소)",
    },
    {
        "pk": 3,
        "group_pk": 1,
        "measurement_item": "co2",
        "warning_max": "1000",
        "danger_max": "5000",
        "unit": "ppm",
        "description": "CO2 (이산화탄소)",
    },
    {
        "pk": 4,
        "group_pk": 1,
        "measurement_item": "o2",
        "warning_min": "18",
        "warning_max": "23.5",
        "danger_min": "16",
        "unit": "%",
        "description": "O2 (산소, 낮을수록 위험)",
    },
    {
        "pk": 5,
        "group_pk": 1,
        "measurement_item": "no2",
        "warning_max": "3",
        "danger_max": "5",
        "unit": "ppm",
        "description": "NO2 (이산화질소)",
    },
    {
        "pk": 6,
        "group_pk": 1,
        "measurement_item": "so2",
        "warning_max": "2",
        "danger_max": "5",
        "unit": "ppm",
        "description": "SO2 (이산화황)",
    },
    {
        "pk": 7,
        "group_pk": 1,
        "measurement_item": "o3",
        "warning_max": "0.06",
        "danger_max": "0.12",
        "unit": "ppm",
        "description": "O3 (오존)",
    },
    {
        "pk": 8,
        "group_pk": 1,
        "measurement_item": "nh3",
        "warning_max": "25",
        "danger_max": "35",
        "unit": "ppm",
        "description": "NH3 (암모니아)",
    },
    {
        "pk": 9,
        "group_pk": 1,
        "measurement_item": "voc",
        "warning_max": "0.5",
        "danger_max": "1.0",
        "unit": "ppm",
        "description": "VOC (휘발성유기화합물)",
    },
    {
        "pk": 10,
        "group_pk": 2,
        "measurement_item": "power_w",
        "warning_max": "2200",
        "danger_max": "2860",
        "unit": "W",
        "description": "전력 와트 (caution 2200, danger 2860)",
    },
]


def seed(apps, schema_editor):
    ThresholdGroup = apps.get_model("facilities", "ThresholdGroup")
    Threshold = apps.get_model("facilities", "Threshold")

    for g in THRESHOLD_GROUPS:
        ThresholdGroup.objects.update_or_create(
            pk=g["pk"],
            defaults={
                "code": g["code"],
                "name": g["name"],
                "description": g["description"],
                "is_active": True,
            },
        )

    for t in THRESHOLDS:
        Threshold.objects.update_or_create(
            pk=t["pk"],
            defaults={
                "group_id": t["group_pk"],
                "measurement_item": t["measurement_item"],
                "warning_min": Decimal(t["warning_min"])
                if "warning_min" in t
                else None,
                "warning_max": Decimal(t["warning_max"])
                if "warning_max" in t
                else None,
                "danger_min": Decimal(t["danger_min"]) if "danger_min" in t else None,
                "danger_max": Decimal(t["danger_max"]) if "danger_max" in t else None,
                "unit": t["unit"],
                "description": t["description"],
                "is_active": True,
            },
        )


def revert(apps, schema_editor):
    Threshold = apps.get_model("facilities", "Threshold")
    ThresholdGroup = apps.get_model("facilities", "ThresholdGroup")
    Threshold.objects.filter(group__code__in=["gas_legal", "power_default"]).delete()
    ThresholdGroup.objects.filter(code__in=["gas_legal", "power_default"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0010_thresholdgroup_threshold"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
