# Generated for alarm-record-integration sprint (2026-05-14)
#
# AlarmRecord 에 ml_anomaly_result FK 추가 — AI 알람 (POWER_ANOMALY_AI 등) 의
# MLAnomalyResult 와 PK join 용. nullable / SET_NULL 이라 기존 데이터 backfill 불필요.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0012_alter_alarmrecord_alarm_type_and_more"),
        ("ml", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="alarmrecord",
            name="ml_anomaly_result",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="alarm_records",
                to="ml.mlanomalyresult",
            ),
        ),
    ]
