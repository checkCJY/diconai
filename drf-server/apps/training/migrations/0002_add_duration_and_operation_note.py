# Manually authored — VRTrainingContent 어드민 기능 도입에 따른 필드 2건 추가.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="vrtrainingcontent",
            name="operation_note",
            field=models.TextField(blank=True, default="", verbose_name="운영 메모"),
        ),
        migrations.AddField(
            model_name="vrtrainingcontent",
            name="duration_seconds",
            field=models.IntegerField(
                blank=True, null=True, verbose_name="재생 시간(초)"
            ),
        ),
    ]
