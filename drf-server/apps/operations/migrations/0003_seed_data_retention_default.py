"""
DataRetentionPolicy 기본 5종 시드 (PR-C).

phase_4_pr3_report.md §7-4 권장 정책:
  (gas_sensor, gas_raw, daily, raw=30, history=90)
  (gas_sensor, gas_anomaly, monthly_15, raw=30, history=365)
  (power, power_raw, daily, raw=30, history=90)
  (power, power_agg, monthly_15, raw=30, history=365)
  (position_node, position_hist, daily, raw=30, history=90)

[idempotent — 운영자 수정 보호]
get_or_create 사용. 마이그 재실행 시 기존 row 발견하면 skip — 운영자가 어드민에서
수정한 값을 덮어쓰지 않음. 새 환경 fresh migrate에서만 신규 row 생성.
"""

from django.db import migrations

DEFAULT_POLICIES = [
    {
        "device_type": "gas_sensor",
        "data_category": "gas_raw",
        "raw_retention_days": 30,
        "history_retention_days": 90,
        "delete_cycle": "daily",
        "memo": "가스 원천 데이터 — 매일 30일 초과 row 삭제",
    },
    {
        "device_type": "gas_sensor",
        "data_category": "gas_anomaly",
        "raw_retention_days": 30,
        "history_retention_days": 365,
        "delete_cycle": "monthly_15",
        "memo": "가스 이상 이력 — 매월 15일 1년 초과 row 삭제",
    },
    {
        "device_type": "power",
        "data_category": "power_raw",
        "raw_retention_days": 30,
        "history_retention_days": 90,
        "delete_cycle": "daily",
        "memo": "전력 원천 데이터 — 매일 30일 초과 row 삭제",
    },
    {
        "device_type": "power",
        "data_category": "power_agg",
        "raw_retention_days": 30,
        "history_retention_days": 365,
        "delete_cycle": "monthly_15",
        "memo": "전력 집계 이력 — 매월 15일 1년 초과 row 삭제",
    },
    {
        "device_type": "position_node",
        "data_category": "position_hist",
        "raw_retention_days": 30,
        "history_retention_days": 90,
        "delete_cycle": "daily",
        "memo": "작업자 위치 이력 — 매일 30일 초과 row 삭제",
    },
]


def seed(apps, schema_editor):
    DataRetentionPolicy = apps.get_model("operations", "DataRetentionPolicy")
    for p in DEFAULT_POLICIES:
        DataRetentionPolicy.objects.get_or_create(
            device_type=p["device_type"],
            data_category=p["data_category"],
            defaults={
                "raw_retention_days": p["raw_retention_days"],
                "history_retention_days": p["history_retention_days"],
                "delete_cycle": p["delete_cycle"],
                "is_active": True,
                "memo": p["memo"],
            },
        )


def revert(apps, schema_editor):
    DataRetentionPolicy = apps.get_model("operations", "DataRetentionPolicy")
    for p in DEFAULT_POLICIES:
        DataRetentionPolicy.objects.filter(
            device_type=p["device_type"], data_category=p["data_category"]
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0002_applog_integrationlog"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
