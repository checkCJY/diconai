"""
DataRetentionPolicy DeviceType + DataCategory choices 확장.

[추가된 DeviceType]
- ml     : AI/ML 모델·추론 결과 (sensor 종류와 무관한 시스템 자산)
- system : 로그·알림 등 도메인 횡단 시스템 데이터

[추가된 DataCategory]
센서 집계 (Phase 4 모델 신설 예정 — 정책 행만 미리 추가)
- gas_hourly      : GasDataHourly 시간 집계
- power_hourly    : PowerDataHourly 시간 집계
AI/ML
- ml_result       : MLAnomalyResult 추론 결과
- ml_model        : MLModel DB행 + .pkl 파일
시스템 로그
- system_log      : SystemLog
- integration_log : IntegrationLog
- app_log         : AppLog
- login_log       : LoginLog
- notification    : Notification 발송 이력

[DB 영향]
CharField choices 변경은 DB 스키마 변경 없음 — Django 레벨 검증만 갱신.
"""

from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0003_seed_data_retention_default"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="dataretentionpolicy",
            name="device_type",
            field=models.CharField(
                choices=[
                    ("gas_sensor", "유해가스 센서"),
                    ("power", "전력"),
                    ("position_node", "위치 노드"),
                    ("ml", "AI/ML"),
                    ("system", "시스템"),
                ],
                max_length=20,
                verbose_name="장비 유형",
            ),
        ),
        migrations.AlterField(
            model_name="dataretentionpolicy",
            name="data_category",
            field=models.CharField(
                choices=[
                    ("gas_raw", "가스 원천 데이터"),
                    ("gas_anomaly", "가스 이상 이력"),
                    ("gas_hourly", "가스 시간 집계"),
                    ("power_raw", "전력 원천 데이터"),
                    ("power_agg", "전력 집계 이력"),
                    ("power_hourly", "전력 시간 집계"),
                    ("position_hist", "위치 이력"),
                    ("ml_result", "AI 추론 결과"),
                    ("ml_model", "AI 모델 파일"),
                    ("system_log", "시스템 로그"),
                    ("integration_log", "연동 로그"),
                    ("app_log", "앱 로그"),
                    ("login_log", "로그인 로그"),
                    ("notification", "알림 이력"),
                ],
                max_length=20,
                verbose_name="데이터 분류",
            ),
        ),
    ]
