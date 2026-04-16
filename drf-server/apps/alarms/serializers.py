from rest_framework import serializers
from .models import AlarmRecord


class AlarmRecordSerializer(serializers.ModelSerializer):
    sensor_name = serializers.SerializerMethodField()
    worker_name = serializers.SerializerMethodField()
    geofence_name = serializers.SerializerMethodField()

    class Meta:
        model = AlarmRecord
        fields = [
            "id",
            "alarm_level",
            "alarm_type",
            "gas_type",
            "measured_value",
            "threshold_value",
            "status",
            "is_active",
            "sensor_name",
            "worker_name",
            "geofence_name",
            "created_at",
            "resolved_at",
        ]

    def get_sensor_name(self, obj):
        return obj.sensor.device_name if obj.sensor else None

    def get_worker_name(self, obj):
        return obj.worker.username if obj.worker else None

    def get_geofence_name(self, obj):
        return obj.geofence.name if obj.geofence else None
