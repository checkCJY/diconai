"""
HazardTypeGroup 6종 + HazardType 10종 시드 (AlarmType 1:1 매핑).

[2026-05-09 PR-A 회귀 점검 후속]
원본은 call_command("loaddata", "hazard_type") 호출이었으나, 동일 위험으로 historical apps
패턴 재작성. fixture json은 보존.

운영 DB는 이미 0005 적용 완료라 본 변경 영향 없음.
"""

from django.db import migrations

HAZARD_TYPE_GROUPS = [
    {"pk": 1, "code": "environment", "name": "환경 위험", "sort_order": 1},
    {"pk": 2, "code": "equipment", "name": "설비 위험", "sort_order": 2},
    {"pk": 3, "code": "location", "name": "위치 위험", "sort_order": 3},
    {"pk": 4, "code": "worker", "name": "작업자 위험", "sort_order": 4},
    {"pk": 5, "code": "operation", "name": "운영 일정", "sort_order": 5},
    {"pk": 6, "code": "system", "name": "시스템", "sort_order": 6},
]

HAZARD_TYPES = [
    {
        "pk": 1,
        "group_id": 1,
        "type_code": "gas_threshold",
        "name": "가스 경보",
        "display_color": "red",
        "map_visible": True,
        "description": "유해가스 임계치 초과",
    },
    {
        "pk": 2,
        "group_id": 2,
        "type_code": "power_overload",
        "name": "전력 이상",
        "display_color": "orange",
        "map_visible": True,
        "description": "전력 과부하/이상 패턴",
    },
    {
        "pk": 3,
        "group_id": 3,
        "type_code": "geofence_intrusion",
        "name": "위험구역 진입",
        "display_color": "red",
        "map_visible": True,
        "description": "지오펜스 위험구역 진입",
    },
    {
        "pk": 4,
        "group_id": 6,
        "type_code": "sensor_fault",
        "name": "센서 이상",
        "display_color": "gray",
        "map_visible": False,
        "description": "센서 통신/측정 이상 (시스템 분류, 정책 화면 비노출)",
    },
    {
        "pk": 5,
        "group_id": 4,
        "type_code": "ppe_violation",
        "name": "PPE 미착용",
        "display_color": "orange",
        "map_visible": True,
        "description": "보호장비 미착용 감지",
    },
    {
        "pk": 6,
        "group_id": 4,
        "type_code": "vr_training_not_done",
        "name": "VR 교육 미이수",
        "display_color": "orange",
        "map_visible": False,
        "description": "필수 VR 교육 미수료",
    },
    {
        "pk": 7,
        "group_id": 4,
        "type_code": "safety_check_pending",
        "name": "체크리스트 미완료",
        "display_color": "orange",
        "map_visible": False,
        "description": "작업 안전 체크리스트 미완료",
    },
    {
        "pk": 8,
        "group_id": 5,
        "type_code": "inspection_scheduled",
        "name": "점검 예정",
        "display_color": "green",
        "map_visible": False,
        "description": "정기 점검 일정 도래",
    },
    {
        "pk": 9,
        "group_id": 6,
        "type_code": "batch_failed",
        "name": "배치 실패",
        "display_color": "orange",
        "map_visible": False,
        "description": "예약 배치 작업 실패",
    },
    {
        "pk": 10,
        "group_id": 5,
        "type_code": "storage_overdue",
        "name": "보관 주기 실패",
        "display_color": "orange",
        "map_visible": False,
        "description": "데이터 보관 정책 미실행",
    },
]


def seed(apps, schema_editor):
    HazardTypeGroup = apps.get_model("alerts", "HazardTypeGroup")
    HazardType = apps.get_model("alerts", "HazardType")

    for g in HAZARD_TYPE_GROUPS:
        HazardTypeGroup.objects.update_or_create(
            pk=g["pk"],
            defaults={
                "code": g["code"],
                "name": g["name"],
                "sort_order": g["sort_order"],
                "is_active": True,
            },
        )

    for h in HAZARD_TYPES:
        HazardType.objects.update_or_create(
            pk=h["pk"],
            defaults={
                "group_id": h["group_id"],
                "type_code": h["type_code"],
                "name": h["name"],
                "display_color": h["display_color"],
                "map_visible": h["map_visible"],
                "description": h["description"],
                "is_active": True,
            },
        )


def revert(apps, schema_editor):
    apps.get_model("alerts", "HazardType").objects.all().delete()
    apps.get_model("alerts", "HazardTypeGroup").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0004_hazardtypegroup_hazardtype_alertpolicy"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
