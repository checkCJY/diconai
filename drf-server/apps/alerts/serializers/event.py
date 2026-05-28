from rest_framework import serializers
from apps.alerts.models import Event
from apps.alerts.serializers.alarm_record import AlarmRecordSerializer


class EventListSerializer(serializers.ModelSerializer):
    alarm_count = serializers.IntegerField(source="alarms.count", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    risk_level_display = serializers.CharField(
        source="get_risk_level_display", read_only=True
    )
    worker_name = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "event_type",
            "risk_level",
            "risk_level_display",
            "status",
            "status_display",
            "source_label",
            "summary",
            "first_detected_at",
            "last_detected_at",
            "alarm_count",
            "worker_name",
        ]

    def get_worker_name(self, obj):
        return obj.worker.get_full_name() or obj.worker.username if obj.worker else None


class EventDetailSerializer(serializers.ModelSerializer):
    alarm_count = serializers.IntegerField(source="alarms.count", read_only=True)
    alarms = AlarmRecordSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    risk_level_display = serializers.CharField(
        source="get_risk_level_display", read_only=True
    )
    worker_name = serializers.SerializerMethodField()
    acknowledged_by_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.SerializerMethodField()
    recommended_actions = serializers.SerializerMethodField()
    source_connection_status = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "event_type",
            "risk_level",
            "risk_level_display",
            "status",
            "status_display",
            "source_label",
            "summary",
            "first_detected_at",
            "last_detected_at",
            "alarm_count",
            "worker_name",
            "acknowledged_by_name",
            "resolved_by_name",
            "acknowledged_at",
            "resolved_at",
            "alarms",
            "recommended_actions",
            "source_connection_status",
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

    def get_recommended_actions(self, obj):
        """연결된 AlertPolicy 의 권고 조치를 risk_level 로 룩업. policy 미연결 또는
        값 부재 시 빈 리스트 (프론트가 fallback 매트릭스 사용)."""
        if not obj.policy or not obj.policy.recommended_actions:
            return []
        actions = obj.policy.recommended_actions
        return actions.get(obj.risk_level) or actions.get("default") or []

    def get_source_connection_status(self, obj):
        """이벤트 발생원의 연결 상태 라벨. 센서/설비는 last_reading 기반 5분 무수신
        판정 + status 필드 조합. 지오펜스는 통신 개념이 없으므로 '활성'. 발생원
        FK 가 모두 비어 있으면 '-' (e.g. system 알림)."""
        device = obj.source_sensor or obj.source_power_device
        if device:
            if device.status == "offline" or device.is_communication_lost:
                return "오프라인"
            if device.status == "error":
                return "오류"
            if device.status == "inactive":
                return "비활성"
            return "정상"
        if obj.source_geofence:
            return "활성"
        return "-"
