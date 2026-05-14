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
        """이벤트 현황 패널 등에 표시할 한국어 요약 메시지.

        원안 디자인 — "산소 농도 정상 범위 이하로 저하" 처럼 도메인 의미가 한눈에
        드러나야 한다. alarm_type 별 분기로 발생원·측정값·임계 단서를 조합.
        """
        if obj.gas_type and obj.measured_value is not None:
            return f"{obj.gas_type.upper()} 임계치 초과 ({obj.measured_value} ppm)"
        if obj.power_device_id and obj.measured_value is not None:
            if obj.alarm_type == "power_anomaly_ai":
                return f"AI 이상 패턴 감지 ({obj.measured_value} W)"
            return f"전력 임계치 초과 ({obj.measured_value} W)"
        if obj.geofence_id:
            return "위험구역 진입"
        if obj.alarm_type == "sensor_fault":
            return "센서 통신 이상"
        # 화면 정책 알람 (PPE, VR 교육 등) — alarm_type 라벨이 이미 한글이라 그대로.
        return (
            obj.get_alarm_type_display()
            if hasattr(obj, "get_alarm_type_display")
            else obj.alarm_type
        )
