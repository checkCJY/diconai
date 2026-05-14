"""AI 이상탐지 알람 forward 입력 serializer.

fastapi `forward_inference_e2e` → POST /alerts/api/anomaly-alarm-records/ 입력 검증.
ml_anomaly_result_id 는 fastapi 가 직전 MLAnomalyResult INSERT 응답에서 추출해 전달.

[현재 sprint 범위: 전력만]
alarm_type choices 는 power_anomaly_ai 만. 가스 (gas_anomaly_ai) 는 enum 정의 후
가스 트랙 후속 sprint 에서 choices 확장 + view 분기 활성화.
"""

from rest_framework import serializers

from apps.core.constants import AlarmType, GasTypeChoices, RiskLevel


class AnomalyAlarmRecordPayloadSerializer(serializers.Serializer):
    alarm_type = serializers.ChoiceField(
        choices=[AlarmType.POWER_ANOMALY_AI],
    )
    risk_level = serializers.ChoiceField(choices=RiskLevel.choices)
    source_device_id = serializers.CharField(required=False, allow_null=True)
    source_sensor_id = serializers.CharField(required=False, allow_null=True)
    gas_type = serializers.ChoiceField(
        choices=GasTypeChoices.choices, required=False, allow_blank=True
    )
    measured_value = serializers.FloatField(required=False, allow_null=True)
    summary = serializers.CharField()
    detected_at = serializers.DateTimeField()
    source_label = serializers.CharField(allow_blank=True)
    ml_anomaly_result_id = serializers.IntegerField(required=False, allow_null=True)
