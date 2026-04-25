# drf-server/apps/geofence/serializers.py
from rest_framework import serializers
from apps.geofence.models import GeoFence


class GeoFenceSerializer(serializers.ModelSerializer):
    """
    GeoFence 직렬화 — 상세 조회용
    """

    class Meta:
        model = GeoFence
        fields = [
            "id",
            "facility",
            "name",
            "polygon",
            "risk_level",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
