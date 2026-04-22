from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="powerevent",
            name="measured_at",
            field=models.DateTimeField(
                verbose_name="측정 시각",
            ),
        ),
        migrations.AddIndex(
            model_name="powerevent",
            index=models.Index(
                fields=["power_device", "-measured_at"],
                name="idx_pwr_evt_dev_meas",
            ),
        ),
    ]
