"""
Phase 4-a — RoleMenuVisibility 자동 시드.

정책:
- super_admin / facility_admin: 모든 SNB 메뉴 visible
- worker: admin_only 및 그 자식(admin_history) 제외 모두 visible
- viewer: worker와 동일 (읽기 권한은 API 레벨)

dependencies: dashboard.0002_seed_menu (Menu 시드) + accounts.0010_seed_role_profile.
"""

from django.db import migrations

ADMIN_ONLY_MENU_CODES = {"admin_only", "admin_history"}


def seed(apps, schema_editor):
    RoleProfile = apps.get_model("accounts", "RoleProfile")
    Menu = apps.get_model("dashboard", "Menu")
    RoleMenuVisibility = apps.get_model("dashboard", "RoleMenuVisibility")

    role_profiles = list(RoleProfile.objects.filter(is_active=True))
    snb_menus = list(Menu.objects.filter(menu_type="snb", is_active=True))

    for role in role_profiles:
        for menu in snb_menus:
            # worker / viewer는 admin_only 그룹 제외
            if role.code in ("worker", "viewer") and menu.code in ADMIN_ONLY_MENU_CODES:
                is_visible = False
            else:
                is_visible = True

            RoleMenuVisibility.objects.get_or_create(
                role_profile=role,
                menu=menu,
                defaults={"is_visible": is_visible},
            )


def revert(apps, schema_editor):
    apps.get_model("dashboard", "RoleMenuVisibility").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0002_seed_menu"),
        ("accounts", "0010_seed_role_profile"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
