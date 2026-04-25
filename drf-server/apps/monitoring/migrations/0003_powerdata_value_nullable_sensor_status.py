from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0002_powerevent_measured_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="powerdata",
            name="value",
            field=models.FloatField(null=True, blank=True, verbose_name="측정값"),
        ),
        migrations.AddField(
            model_name="powerdata",
            name="sensor_status",
            field=models.CharField(
                max_length=20,
                choices=[("active", "정상"), ("comm_failure", "통신 불능")],
                default="active",
                verbose_name="센서 통신 상태",
            ),
        ),
    ]
