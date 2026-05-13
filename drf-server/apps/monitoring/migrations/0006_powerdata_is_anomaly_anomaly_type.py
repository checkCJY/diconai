# Generated for Phase 3 (IF 학습용 라벨링 필드)

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0005_powerevent_updated_at_powerevent_updated_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="powerdata",
            name="is_anomaly",
            field=models.BooleanField(
                default=False,
                help_text="더미 시뮬레이터/운영자 라벨링용",
                verbose_name="이상 라벨",
            ),
        ),
        migrations.AddField(
            model_name="powerdata",
            name="anomaly_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("overload", "과부하"),
                    ("voltage_drop", "저전압"),
                    ("spike", "스파이크"),
                    ("phase_loss", "결상"),
                    ("degradation", "열화"),
                ],
                help_text="더미 시뮬레이터 시나리오 라벨 — IF 학습 평가용",
                max_length=20,
                null=True,
                verbose_name="이상 시나리오",
            ),
        ),
        migrations.AddIndex(
            model_name="powerdata",
            index=models.Index(
                fields=["is_anomaly", "-measured_at"],
                name="idx_pwr_anomaly_time",
            ),
        ),
    ]
