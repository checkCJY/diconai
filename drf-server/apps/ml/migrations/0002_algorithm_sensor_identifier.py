# ARIMA un-downgrade plan §4 (W1) — MLModel 스키마 변경.
#  - model_type → algorithm RenameField (데이터 보존) + ARIMA choice 추가
#  - sensor_identifier 신규 (기존 row 빈 문자열 default → IF 회귀 0)
#  - 제약 변경: 2축(sensor_type, version) → 4축(sensor_type, algorithm,
#    sensor_identifier, version) unique + 활성 모델 매칭 단위 1건 제약

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ml", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="mlmodel",
            old_name="model_type",
            new_name="algorithm",
        ),
        migrations.AlterField(
            model_name="mlmodel",
            name="algorithm",
            field=models.CharField(
                choices=[
                    ("isolation_forest", "Isolation Forest"),
                    ("arima", "ARIMA"),
                ],
                default="isolation_forest",
                max_length=30,
                verbose_name="모델 알고리즘",
            ),
        ),
        migrations.AddField(
            model_name="mlmodel",
            name="sensor_identifier",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "ARIMA 등 단일 시계열 모델용. 예: 'power:device_1:ch3:watt'. "
                    "비어 있으면 sensor_type 단위 (전 sensor 공유)."
                ),
                max_length=64,
                verbose_name="센서 식별자",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="mlmodel",
            name="uq_ml_model_sensor_version",
        ),
        migrations.AddConstraint(
            model_name="mlmodel",
            constraint=models.UniqueConstraint(
                fields=("sensor_type", "algorithm", "sensor_identifier", "version"),
                name="uq_ml_model_sensor_alg_id_version",
            ),
        ),
        migrations.AddConstraint(
            model_name="mlmodel",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("sensor_type", "algorithm", "sensor_identifier"),
                name="uq_ml_model_active_per_match_unit",
            ),
        ),
        migrations.AlterField(
            model_name="mlmodel",
            name="is_active",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "추론에 사용할 모델 1개당 1건만 True "
                    "((sensor_type, algorithm, sensor_identifier) 단위)"
                ),
                verbose_name="활성 모델",
            ),
        ),
        migrations.AlterField(
            model_name="mlmodel",
            name="version",
            field=models.PositiveIntegerField(
                help_text=(
                    "동일 (sensor_type, algorithm, sensor_identifier) "
                    "안에서 1부터 순차 증가"
                ),
                verbose_name="모델 버전",
            ),
        ),
    ]
