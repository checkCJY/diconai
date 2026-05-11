"""
Phase 4-a — UserType 4종 RoleProfile 자동 시드.

운영자가 어드민에서 추가 RoleProfile 만들 수 있지만, dashboard 메뉴 트리
DB 조회 전환을 위해 기본 4종(super_admin/facility_admin/worker/viewer)은 자동 생성.

forward: code = UserType.values 그대로 4 row.
reverse: 본 마이그가 만든 4 row 삭제.
"""

from django.db import migrations

ROLE_PROFILES = [
    {
        "code": "super_admin",
        "name": "슈퍼관리자",
        "base_user_type": "super_admin",
        "platform_type": "web",
    },
    {
        "code": "facility_admin",
        "name": "관리자",
        "base_user_type": "facility_admin",
        "platform_type": "web",
    },
    {
        "code": "worker",
        "name": "일반사용자",
        "base_user_type": "worker",
        "platform_type": "app",
    },
    {
        "code": "viewer",
        "name": "열람자",
        "base_user_type": "viewer",
        "platform_type": "web",
    },
]


def seed(apps, schema_editor):
    RoleProfile = apps.get_model("accounts", "RoleProfile")
    for r in ROLE_PROFILES:
        RoleProfile.objects.get_or_create(
            code=r["code"],
            defaults={
                "name": r["name"],
                "base_user_type": r["base_user_type"],
                "platform_type": r["platform_type"],
                "description": "Phase 4-a 자동 시드",
                "is_active": True,
            },
        )


def revert(apps, schema_editor):
    RoleProfile = apps.get_model("accounts", "RoleProfile")
    RoleProfile.objects.filter(code__in=[r["code"] for r in ROLE_PROFILES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_roleprofile"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
