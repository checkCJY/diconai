from rest_framework import serializers
from apps.alerts.models import AlarmRecord


class AlarmRecordSerializer(serializers.ModelSerializer):
    sensor_name = serializers.SerializerMethodField()
    power_device_name = serializers.SerializerMethodField()
    worker_name = serializers.SerializerMethodField()
    geofence_name = serializers.SerializerMethodField()
    alarm_level = serializers.CharField(source="risk_level")
    message = serializers.SerializerMethodField()

    class Meta:
        model = AlarmRecord
        fields = [
            "id",
            "alarm_type",
            "risk_level",
            "alarm_level",
            "gas_type",
            "measured_value",
            "threshold_value",
            "message",
            "sensor_name",
            "power_device_name",
            "worker_name",
            "geofence_name",
            "event",
            "created_at",
            # W4.a — AI 알람 algorithm 출처 (isolation_forest / arima / combined /
            # night_abnormal / "" / NULL). UI 가 별도 칩 표시 가능.
            "algorithm_source",
        ]

    def get_sensor_name(self, obj):
        return obj.sensor.device_name if obj.sensor else None

    def get_power_device_name(self, obj):
        return obj.power_device.device_name if obj.power_device else None

    def get_worker_name(self, obj):
        return obj.worker.username if obj.worker else None

    def get_geofence_name(self, obj):
        return obj.geofence.name if obj.geofence else None

    def get_message(self, obj):
        """이벤트 현황 패널 등에 표시할 한 줄 메시지.

        실제 분기는 AlarmRecord.get_short_message() 가 single source of truth.
        WS push payload (apps.alerts.tasks._push_to_ws) 도 같은 메서드를 호출하므로
        API 응답과 실시간 push 가 같은 텍스트를 노출 (drift 방지).
        """
        return obj.get_short_message()
