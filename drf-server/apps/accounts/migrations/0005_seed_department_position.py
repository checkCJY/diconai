from django.db import migrations

DEPARTMENTS = [
    ("경영지원팀", "MGMT"),
    ("영업팀", "SALES"),
    ("사업기획팀", "BIZ"),
    ("기술연구소", "RND"),
    ("개발팀", "DEV"),
    ("관제운영팀", "OPS"),
    ("시스템운영팀", "SYS"),
    ("안전관리팀", "SAFE"),
    ("품질관리팀", "QA"),
    ("생산관리팀", "PROD"),
    ("설치공사팀", "INST"),
    ("유지보수팀", "MAINT"),
    ("고객지원팀", "CS"),
]

# (name, level, category)
POSITIONS = [
    # 사무직
    ("사원", 1, "office"),
    ("대리", 2, "office"),
    ("과장", 3, "office"),
    ("차장", 4, "office"),
    ("부장", 5, "office"),
    # 현장직
    ("사원(작업자)", 11, "field"),
    ("조장", 12, "field"),
    ("반장", 13, "field"),
    ("현장소장", 14, "field"),
    # 임원진
    ("이사", 21, "executive"),
    ("상무", 22, "executive"),
    ("전무", 23, "executive"),
    ("대표이사", 24, "executive"),
]


def seed_forward(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    Position = apps.get_model("accounts", "Position")

    Department.objects.bulk_create(
        [Department(name=name, code=code, is_active=True) for name, code in DEPARTMENTS]
    )
    Position.objects.bulk_create(
        [
            Position(name=name, level=level, category=category, is_active=True)
            for name, level, category in POSITIONS
        ]
    )


def seed_backward(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    Position = apps.get_model("accounts", "Position")
    Department.objects.all().delete()
    Position.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_department_position_customuser_name_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
