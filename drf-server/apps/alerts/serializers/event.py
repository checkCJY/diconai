from rest_framework import serializers
from apps.alerts.models import Event
from apps.alerts.serializers.alarm_record import AlarmRecordSerializer


class EventListSerializer(serializers.ModelSerializer):
    alarm_count       = serializers.IntegerField(source='alarms.count', read_only=True)
    status_display    = serializers.CharField(source='get_status_display', read_only=True)
    risk_level_display = serializers.CharField(source='get_risk_level_display', read_only=True)
    worker_name       = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id', 'event_type', 'risk_level', 'risk_level_display',
            'status', 'status_display', 'source_label', 'summary',
            'first_detected_at', 'last_detected_at', 'alarm_count', 'worker_name',
        ]

    def get_worker_name(self, obj):
        return obj.worker.get_full_name() or obj.worker.username if obj.worker else None


class EventDetailSerializer(serializers.ModelSerializer):
    alarm_count        = serializers.IntegerField(source='alarms.count', read_only=True)
    alarms             = AlarmRecordSerializer(many=True, read_only=True)
    status_display     = serializers.CharField(source='get_status_display', read_only=True)
    risk_level_display = serializers.CharField(source='get_risk_level_display', read_only=True)
    worker_name        = serializers.SerializerMethodField()
    acknowledged_by_name = serializers.SerializerMethodField()
    resolved_by_name   = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id', 'event_type', 'risk_level', 'risk_level_display',
            'status', 'status_display', 'source_label', 'summary',
            'first_detected_at', 'last_detected_at', 'alarm_count',
            'worker_name', 'acknowledged_by_name', 'resolved_by_name',
            'acknowledged_at', 'resolved_at', 'alarms',
        ]

    def get_worker_name(self, obj):
        return obj.worker.get_full_name() or obj.worker.username if obj.worker else None

    def get_acknowledged_by_name(self, obj):
        if not obj.acknowledged_by:
            return None
        return obj.acknowledged_by.get_full_name() or obj.acknowledged_by.username

    def get_resolved_by_name(self, obj):
        if not obj.resolved_by:
            return None
        return obj.resolved_by.get_full_name() or obj.resolved_by.username
