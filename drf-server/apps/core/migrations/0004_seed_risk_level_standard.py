"""
RiskLevelStandard 3종 시드 (normal / warning / danger).

[2026-05-09 PR-A 회귀 점검 후속]
원본은 call_command("loaddata", "risk_level_standard") 호출이었으나, fixture는 이후
마이그가 새 NOT NULL 필드를 추가할 때 fresh migrate에서 깨짐. historical apps.get_model
기반 explicit update_or_create로 재작성 (Step 2 fix 0011 패턴 일관).

운영 DB는 이미 0004 적용 완료라 본 변경 영향 없음.
"""

from django.db import migrations

RISK_LEVELS = [
    {
        "pk": 1,
        "code": "normal",
        "name": "정상",
        "display_color": "green",
        "alert_intensity": "normal",
        "event_priority": 1,
        "description": "정상 운영 상태",
    },
    {
        "pk": 2,
        "code": "warning",
        "name": "주의",
        "display_color": "orange",
        "alert_intensity": "warning",
        "event_priority": 2,
        "description": "임계치 근접 — 모니터링 강화 필요",
    },
    {
        "pk": 3,
        "code": "danger",
        "name": "위험",
        "display_color": "red",
        "alert_intensity": "urgent",
        "event_priority": 3,
        "description": "임계치 초과 — 즉시 조치 필요",
    },
]


def seed(apps, schema_editor):
    RiskLevelStandard = apps.get_model("core", "RiskLevelStandard")
    for r in RISK_LEVELS:
        RiskLevelStandard.objects.update_or_create(
            pk=r["pk"],
            defaults={
                "code": r["code"],
                "name": r["name"],
                "display_color": r["display_color"],
                "alert_intensity": r["alert_intensity"],
                "event_priority": r["event_priority"],
                "description": r["description"],
                "is_active": True,
            },
        )


def revert(apps, schema_editor):
    apps.get_model("core", "RiskLevelStandard").objects.filter(
        code__in=["normal", "warning", "danger"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_systemlog_result_systemlog_target_menu_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
