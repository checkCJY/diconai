from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="last_notified_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="마지막 알림 발송 시각",
            ),
        ),
    ]
