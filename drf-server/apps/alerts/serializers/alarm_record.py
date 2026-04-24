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
        if obj.gas_type and obj.measured_value is not None:
            return f"{obj.gas_type.upper()} 임계치 초과 ({obj.measured_value} ppm)"
        return obj.alarm_type
