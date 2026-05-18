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
        # 이성현 추가. GAS_ANOMALY_AI 추가
        choices=[AlarmType.POWER_ANOMALY_AI, AlarmType.GAS_ANOMALY_AI]
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
    # PowerDevice 알람 시 채널 (1~16). 가스는 NULL 허용. AlarmRecord.channel 에 저장 →
    # get_short_message 가 channel + power_device.channel_meta 로 라벨 ("송풍기A") 생성.
    channel = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=255
    )
    # W4.a — AI 알고리즘 출처 라벨 (ARIMA un-downgrade plan §8). 본 view 경유 알람은
    # 모두 AI 알람이라 일반적으로 비어있지 않음. 값: isolation_forest / arima /
    # combined / night_abnormal. 옛 fastapi 가 미전송 시 default "" 로 저장.
    algorithm_source = serializers.CharField(
        required=False, allow_blank=True, max_length=30, default=""
    )
