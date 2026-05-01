"""
0007: department.created_at null=True → null=False 전환 + 관련 필드 정리.
0006에서 기존 데이터 호환을 위해 null=True로 추가했던 것을 최종 정리.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def fill_null_created_at(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    Department.objects.filter(created_at__isnull=True).update(created_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_company_userdepartment_refactor"),
        settings.AUTH_USER_MODEL.split(".")[0]
        and ("accounts", "0006_company_userdepartment_refactor"),
    ]

    dependencies = [
        ("accounts", "0006_company_userdepartment_refactor"),
    ]

    operations = [
        migrations.RunPython(fill_null_created_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="department",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="생성일"),
        ),
        migrations.AlterField(
            model_name="department",
            name="name",
            field=models.CharField(max_length=100, verbose_name="부서명"),
        ),
        migrations.AlterField(
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
        migrations.AlterField(
            model_name="company",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_company_set",
                to=settings.AUTH_USER_MODEL,
                verbose_name="최근 수정자",
            ),
        ),
        migrations.AlterField(
            model_name="userdepartment",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
    ]
