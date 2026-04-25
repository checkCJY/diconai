# apps/geofence/serializers/admin_serializers.py
from rest_framework import serializers
from apps.geofence.models import GeoFence


class GeoFenceAdminSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    worker_count = serializers.SerializerMethodField()

    class Meta:
        model = GeoFence
        fields = [
            "id",
            "name",
            "facility",
            "facility_name",
            "risk_level",
            "polygon",
            "description",
            "is_active",
            "created_at",
            "worker_count",
        ]
        read_only_fields = ["id", "created_at"]

    def get_worker_count(self, obj):
        """현재 이 지오펜스에 있는 작업자 수 (최근 5분 이내)"""
        from django.utils import timezone
        from datetime import timedelta
        from apps.positioning.models import WorkerPosition

        since = timezone.now() - timedelta(minutes=5)
        return (
            WorkerPosition.objects.filter(
                current_geofence=obj,
                received_at__gte=since,
            )
            .values("worker")
            .distinct()
            .count()
        )

    def validate_polygon(self, value):
        if len(value) < 3:
            raise serializers.ValidationError(
                "polygon은 최소 3개 이상의 좌표가 필요합니다."
            )
        return value
