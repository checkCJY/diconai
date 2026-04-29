# apps/facilities/serializers/map_editor.py
import math
from rest_framework import serializers

from apps.facilities.models import Facility, GasSensor, PowerDevice, PositionNode
from apps.geofence.models import GeoFence


class FacilityMapSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    code = serializers.SerializerMethodField()
    placed = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "facility"

    def get_code(self, obj):
        return f"FAC-{obj.id:03d}"

    def get_placed(self, obj):
        return obj.map_x is not None

    class Meta:
        model = Facility
        fields = [
            "id",
            "type",
            "code",
            "name",
            "map_x",
            "map_y",
            "map_width",
            "map_height",
            "placed",
        ]


class GasSensorMapSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    code = serializers.SerializerMethodField()
    placed = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "gas_sensor"

    def get_code(self, obj):
        return obj.device_id

    def get_placed(self, obj):
        return True  # DeviceBase는 항상 x, y 보유

    class Meta:
        model = GasSensor
        fields = [
            "id",
            "type",
            "code",
            "device_name",
            "x",
            "y",
            "facility_id",
            "placed",
        ]


class PowerDeviceMapSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    code = serializers.SerializerMethodField()
    placed = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "power_device"

    def get_code(self, obj):
        return obj.device_id

    def get_placed(self, obj):
        return True

    class Meta:
        model = PowerDevice
        fields = [
            "id",
            "type",
            "code",
            "device_name",
            "x",
            "y",
            "facility_id",
            "placed",
        ]


class PositionNodeMapSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    code = serializers.SerializerMethodField()
    placed = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "position_node"

    def get_code(self, obj):
        return obj.device_id

    def get_placed(self, obj):
        return True

    class Meta:
        model = PositionNode
        fields = [
            "id",
            "type",
            "code",
            "device_name",
            "x",
            "y",
            "facility_id",
            "placed",
        ]


class GeoFenceMapSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    placed = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "geofence"

    def get_placed(self, obj):
        return True

    class Meta:
        model = GeoFence
        fields = [
            "id",
            "type",
            "name",
            "risk_level",
            "shape_type",
            "polygon",
            "circle_cx",
            "circle_cy",
            "circle_radius",
            "facility_id",
            "placed",
        ]


# ── 일괄 저장 입력 시리얼라이저 ──────────────────────────────────────────────


class FacilityPositionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    map_x = serializers.FloatField()
    map_y = serializers.FloatField()
    map_width = serializers.FloatField()
    map_height = serializers.FloatField()


class DevicePositionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    x = serializers.FloatField()
    y = serializers.FloatField()


def circle_to_polygon(cx, cy, radius, segments=32):
    """원형 지오펜스를 N각형 polygon으로 근사 변환 (백엔드 거리 계산에 사용)."""
    pts = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        pts.append(
            [
                round(cx + radius * math.cos(angle), 2),
                round(cy + radius * math.sin(angle), 2),
            ]
        )
    return pts


class GeoFenceSaveSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)  # None = 신규
    name = serializers.CharField(max_length=50, allow_blank=True)
    risk_level = serializers.ChoiceField(choices=["danger", "warning", "normal"])
    shape_type = serializers.ChoiceField(
        choices=["polygon", "circle"], default="polygon"
    )
    polygon = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField()), required=False
    )
    circle_cx = serializers.FloatField(required=False, allow_null=True)
    circle_cy = serializers.FloatField(required=False, allow_null=True)
    circle_radius = serializers.FloatField(required=False, allow_null=True)
    facility_id = serializers.IntegerField()
    deleted = serializers.BooleanField(default=False)


class MapEditorSaveSerializer(serializers.Serializer):
    facilities = FacilityPositionSerializer(many=True, default=list)
    gas_sensors = DevicePositionSerializer(many=True, default=list)
    power_devices = DevicePositionSerializer(many=True, default=list)
    position_nodes = DevicePositionSerializer(many=True, default=list)
    geofences = GeoFenceSaveSerializer(many=True, default=list)
