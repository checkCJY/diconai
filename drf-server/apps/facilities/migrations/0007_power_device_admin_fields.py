from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def fill_power_device_codes(apps, schema_editor):
    PowerDevice = apps.get_model("facilities", "PowerDevice")
    existing_codes = set(
        PowerDevice.objects.exclude(device_code="").values_list(
            "device_code", flat=True
        )
    )
    used_nums = set()
    for code in existing_codes:
        try:
            used_nums.add(int(code))
        except (ValueError, TypeError):
            pass

    next_num = 1
    for device in PowerDevice.objects.filter(device_code="").order_by("id"):
        while next_num in used_nums:
            next_num += 1
        device.device_code = f"{next_num:03d}"
        device.save(update_fields=["device_code"])
        used_nums.add(next_num)
        next_num += 1


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0006_gas_sensor_device_code_unique"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. device_code nullable로 먼저 추가
        migrations.AddField(
            model_name="powerdevice",
            name="device_code",
            field=models.CharField(
                blank=True, default="", max_length=10, verbose_name="장비 코드"
            ),
        ),
        # 2. 기존 데이터 채우기
        migrations.RunPython(fill_power_device_codes, migrations.RunPython.noop),
        # 3. unique 제약 적용
        migrations.AlterField(
            model_name="powerdevice",
            name="device_code",
            field=models.CharField(
                max_length=10, unique=True, verbose_name="장비 코드"
            ),
        ),
        # 4. 관리 필드 추가
        migrations.AddField(
            model_name="powerdevice",
            name="department",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="power_devices",
                to="accounts.department",
                verbose_name="관리 부서",
            ),
        ),
        migrations.AddField(
            model_name="powerdevice",
            name="manager",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="managed_power_devices",
                to=settings.AUTH_USER_MODEL,
                verbose_name="관리 담당자",
            ),
        ),
        migrations.AddField(
            model_name="powerdevice",
            name="ip_address",
            field=models.CharField(
                blank=True, default="", max_length=45, verbose_name="통신 IP"
            ),
        ),
        migrations.AddField(
            model_name="powerdevice",
            name="port",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="통신 PORT"
            ),
        ),
        migrations.AddField(
            model_name="powerdevice",
            name="connection_checked_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="마지막 연결 확인일시"
            ),
        ),
        migrations.AddField(
            model_name="powerdevice",
            name="connection_ok",
            field=models.BooleanField(
                blank=True, null=True, verbose_name="연결 확인 결과"
            ),
        ),
        migrations.AddField(
            model_name="powerdevice",
            name="notes",
            field=models.TextField(blank=True, default="", verbose_name="비고"),
        ),
        # 5. PowerDeviceInspection 테이블 생성
        migrations.CreateModel(
            name="PowerDeviceInspection",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                (
                    "inspection_type",
                    models.CharField(
                        choices=[("regular", "정기"), ("abnormal", "이상")],
                        default="regular",
                        max_length=20,
                        verbose_name="점검 유형",
                    ),
                ),
                ("inspection_date", models.DateField(verbose_name="점검일")),
                (
                    "status",
                    models.CharField(
                        choices=[("action_needed", "조치 필요"), ("normal", "정상")],
                        default="normal",
                        max_length=20,
                        verbose_name="점검 결과",
                    ),
                ),
                (
                    "notes",
                    models.TextField(blank=True, default="", verbose_name="점검 내용"),
                ),
                (
                    "expected_action_date",
                    models.DateField(blank=True, null=True, verbose_name="조치 예정일"),
                ),
                (
                    "is_actioned",
                    models.BooleanField(default=False, verbose_name="조치 완료"),
                ),
                (
                    "action_date",
                    models.DateField(blank=True, null=True, verbose_name="조치 완료일"),
                ),
                (
                    "action_notes",
                    models.TextField(blank=True, default="", verbose_name="조치 내용"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inspections",
                        to="facilities.powerdevice",
                        verbose_name="전력 장치",
                    ),
                ),
                (
                    "inspector",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="power_inspections",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="점검자",
                    ),
                ),
                (
                    "action_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="power_action_inspections",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="조치자",
                    ),
                ),
            ],
            options={
                "db_table": "power_device_inspection",
                "ordering": ["-inspection_date", "-created_at"],
            },
        ),
    ]
