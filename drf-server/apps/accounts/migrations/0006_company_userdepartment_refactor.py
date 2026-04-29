"""
0006: Company 모델 추가, Department 확장, UserDepartment(M:N) 도입,
      CustomUser.department FK 제거 + 기존 데이터 UserDepartment로 이전.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_department_data(apps, schema_editor):
    """기존 CustomUser.department_id → UserDepartment(is_primary=True)로 이전."""
    CustomUser = apps.get_model("accounts", "CustomUser")
    UserDepartment = apps.get_model("accounts", "UserDepartment")

    entries = []
    for user in CustomUser.objects.filter(department_id__isnull=False):
        entries.append(
            UserDepartment(
                user_id=user.id,
                department_id=user.department_id,
                is_primary=True,
            )
        )
    if entries:
        UserDepartment.objects.bulk_create(entries, ignore_conflicts=True)


def reverse_migrate_department_data(apps, schema_editor):
    """롤백: UserDepartment(is_primary=True) → CustomUser.department_id 복원."""
    CustomUser = apps.get_model("accounts", "CustomUser")
    UserDepartment = apps.get_model("accounts", "UserDepartment")

    for membership in UserDepartment.objects.filter(is_primary=True).select_related(
        "user"
    ):
        CustomUser.objects.filter(pk=membership.user_id).update(
            department_id=membership.department_id
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_seed_department_position"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. Company 테이블 생성 ───────────────────────────────
        migrations.CreateModel(
            name="Company",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="생성일"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="최근 수정일"),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=100, unique=True, verbose_name="회사명"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="사용 여부"),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_company_set",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="최근 수정자",
                    ),
                ),
            ],
            options={"db_table": "company", "verbose_name": "회사"},
        ),
        # ── 2. Department 필드 추가 ──────────────────────────────
        migrations.AddField(
            model_name="department",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="departments",
                to="accounts.company",
                verbose_name="회사",
            ),
        ),
        migrations.AddField(
            model_name="department",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="children",
                to="accounts.department",
                verbose_name="상위 부서",
            ),
        ),
        migrations.AddField(
            model_name="department",
            name="leader",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="leading_departments",
                to=settings.AUTH_USER_MODEL,
                verbose_name="조직장",
            ),
        ),
        migrations.AddField(
            model_name="department",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True, verbose_name="생성일", null=True
            ),
        ),
        migrations.AddField(
            model_name="department",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="최근 수정일"),
        ),
        migrations.AddField(
            model_name="department",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_department_set",
                to=settings.AUTH_USER_MODEL,
                verbose_name="최근 수정자",
            ),
        ),
        # ── 3. UserDepartment 테이블 생성 ────────────────────────
        migrations.CreateModel(
            name="UserDepartment",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                (
                    "is_primary",
                    models.BooleanField(default=True, verbose_name="주 소속 여부"),
                ),
                (
                    "joined_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="소속 시작일"),
                ),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="accounts.department",
                        verbose_name="부서",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dept_memberships",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="사용자",
                    ),
                ),
            ],
            options={
                "db_table": "user_department",
                "verbose_name": "사용자-부서 소속",
                "unique_together": {("user", "department")},
            },
        ),
        # ── 4. 데이터 이전: department_id → UserDepartment ───────
        migrations.RunPython(
            migrate_department_data,
            reverse_code=reverse_migrate_department_data,
        ),
        # ── 5. CustomUser.department FK 제거 ─────────────────────
        migrations.RemoveField(
            model_name="customuser",
            name="department",
        ),
    ]
