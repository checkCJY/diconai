from django.db import migrations


def convert_minus1_to_null(apps, schema_editor):
    """기존 value=-1(통신 불능) 행을 value=NULL, sensor_status='comm_failure'로 변환."""
    PowerData = apps.get_model("monitoring", "PowerData")
    PowerData.objects.filter(value=-1).update(value=None, sensor_status="comm_failure")


def revert_null_to_minus1(apps, schema_editor):
    """롤백: value=NULL, sensor_status='comm_failure' 행을 value=-1로 복원."""
    PowerData = apps.get_model("monitoring", "PowerData")
    PowerData.objects.filter(sensor_status="comm_failure").update(
        value=-1, sensor_status="active"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0003_powerdata_value_nullable_sensor_status"),
    ]

    operations = [
        migrations.RunPython(
            convert_minus1_to_null, reverse_code=revert_null_to_minus1
        ),
    ]
