# Manually authored — VR 교육 완료 시각 추적 필드 추가.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("safety", "0011_safetystatus_updated_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="safetychecksession",
            name="vr_completed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "작업자가 VR 영상 끝까지 시청해 완료 처리한 시각. NULL=미완료."
                ),
                verbose_name="VR 교육 완료 시각",
            ),
        ),
    ]
