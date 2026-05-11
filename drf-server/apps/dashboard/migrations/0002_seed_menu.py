"""
Menu 12종 시드 (snake_case 코드 — Phase 2-c 변환).

[2026-05-09 PR-A 회귀 점검 후속]
원본은 call_command("loaddata", "menu") 호출이었으나, 동일 위험으로 historical apps 패턴
재작성. parent self-FK는 부모 row 먼저 생성 후 자식이 parent_id 참조.

운영 DB는 이미 0002 적용 완료라 본 변경 영향 없음.
"""

from django.db import migrations

# parent_id 사용 (FK 객체가 아닌 정수). 부모 row가 먼저 생성되어야 함.
MENUS = [
    # 부모 — parent_id=None
    {
        "pk": 1,
        "code": "safety",
        "name": "나의 정보 확인",
        "parent_id": None,
        "menu_type": "snb",
        "sort_order": 10,
        "icon": "shield",
        "url_path": "",
    },
    {
        "pk": 5,
        "code": "monitoring",
        "name": "모니터링",
        "parent_id": None,
        "menu_type": "snb",
        "sort_order": 20,
        "icon": "monitor",
        "url_path": "",
    },
    {
        "pk": 11,
        "code": "admin_only",
        "name": "관리자 전용",
        "parent_id": None,
        "menu_type": "snb",
        "sort_order": 90,
        "icon": "settings",
        "url_path": "",
    },
    # 자식 — parent_id=1
    {
        "pk": 2,
        "code": "profile",
        "name": "나의 프로필",
        "parent_id": 1,
        "menu_type": "snb",
        "sort_order": 11,
        "icon": "",
        "url_path": "/dashboard/profile/",
    },
    {
        "pk": 3,
        "code": "safety_checklist",
        "name": "작업 전 안전 확인",
        "parent_id": 1,
        "menu_type": "snb",
        "sort_order": 12,
        "icon": "",
        "url_path": "/dashboard/safety/checklist/",
    },
    {
        "pk": 4,
        "code": "safety_history",
        "name": "안전 확인 이력",
        "parent_id": 1,
        "menu_type": "snb",
        "sort_order": 13,
        "icon": "",
        "url_path": "/dashboard/safety/history/",
    },
    # 자식 — parent_id=5
    {
        "pk": 6,
        "code": "monitoring_realtime",
        "name": "실시간 모니터링",
        "parent_id": 5,
        "menu_type": "snb",
        "sort_order": 21,
        "icon": "",
        "url_path": "/dashboard/monitoring/realtime/",
    },
    {
        "pk": 7,
        "code": "monitoring_gas",
        "name": "실시간/AI 예측 유해가스 현황",
        "parent_id": 5,
        "menu_type": "snb",
        "sort_order": 22,
        "icon": "",
        "url_path": "/dashboard/monitoring/gas/",
    },
    {
        "pk": 8,
        "code": "monitoring_power",
        "name": "실시간/AI 예측 스마트 전력 현황",
        "parent_id": 5,
        "menu_type": "snb",
        "sort_order": 23,
        "icon": "",
        "url_path": "/dashboard/monitoring/power/",
    },
    {
        "pk": 9,
        "code": "monitoring_workers",
        "name": "작업자 현황",
        "parent_id": 5,
        "menu_type": "snb",
        "sort_order": 24,
        "icon": "",
        "url_path": "/dashboard/monitoring/workers/",
    },
    {
        "pk": 10,
        "code": "monitoring_events",
        "name": "이벤트 현황",
        "parent_id": 5,
        "menu_type": "snb",
        "sort_order": 25,
        "icon": "",
        "url_path": "/dashboard/monitoring/events/",
    },
    # 자식 — parent_id=11
    {
        "pk": 12,
        "code": "admin_history",
        "name": "전체 이력 현황",
        "parent_id": 11,
        "menu_type": "snb",
        "sort_order": 91,
        "icon": "",
        "url_path": "/admin-panel/accounts-management/",
    },
]


def seed(apps, schema_editor):
    Menu = apps.get_model("dashboard", "Menu")
    for m in MENUS:
        Menu.objects.update_or_create(
            pk=m["pk"],
            defaults={
                "code": m["code"],
                "name": m["name"],
                "parent_id": m["parent_id"],
                "menu_type": m["menu_type"],
                "sort_order": m["sort_order"],
                "icon": m["icon"],
                "url_path": m["url_path"],
                "is_active": True,
            },
        )


def revert(apps, schema_editor):
    apps.get_model("dashboard", "Menu").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
