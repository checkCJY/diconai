from django.db import migrations, models


def fill_empty_device_codes(apps, schema_editor):
    GasSensor = apps.get_model("facilities", "GasSensor")
    existing_codes = set(
        GasSensor.objects.exclude(device_code="").values_list("device_code", flat=True)
    )
    used_nums = set()
    for code in existing_codes:
        try:
            used_nums.add(int(code))
        except (ValueError, TypeError):
            pass

    next_num = 1
    for sensor in GasSensor.objects.filter(device_code="").order_by("id"):
        while next_num in used_nums:
            next_num += 1
        sensor.device_code = f"{next_num:03d}"
        sensor.save(update_fields=["device_code"])
        used_nums.add(next_num)
        next_num += 1


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0005_gas_sensor_fields_inspection"),
    ]

    operations = [
        migrations.RunPython(fill_empty_device_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="gassensor",
            name="device_code",
            field=models.CharField(
                max_length=10, unique=True, verbose_name="장비 코드"
            ),
        ),
    ]
