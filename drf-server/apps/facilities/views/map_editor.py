# apps/facilities/views/map_editor.py
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.views.generic import TemplateView
from django.db import transaction

from apps.facilities.models import Facility, GasSensor, PowerDevice, PositionNode
from apps.geofence.models import GeoFence
from apps.facilities.serializers.map_editor import (
    FacilityMapSerializer,
    GasSensorMapSerializer,
    PowerDeviceMapSerializer,
    PositionNodeMapSerializer,
    GeoFenceMapSerializer,
    MapEditorSaveSerializer,
    circle_to_polygon,
)


class MapEditorPageView(TemplateView):
    template_name = "admin_panel/map_editor/map_editor.html"
    extra_context = {"active_nav": "map_editor"}


class MapEditorObjectsView(APIView):
    """
    GET /api/map-editor/objects/?facility_id=1
    지도 편집에 필요한 모든 객체를 한 번에 반환한다.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Map Editor"],
        summary="지도 편집 — 모든 객체 일괄 조회",
        description="공장·가스센서·전력장치·위치노드·지오펜스를 한 번의 호출로 반환. 지도 편집기 초기 로드용.",
        parameters=[
            OpenApiParameter(
                name="facility_id", type=int, required=False, description="공장 ID 필터"
            )
        ],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="MapEditorObjects",
                fields={
                    "facilities": serializers.ListField(child=serializers.DictField()),
                    "gas_sensors": serializers.ListField(child=serializers.DictField()),
                    "power_devices": serializers.ListField(
                        child=serializers.DictField()
                    ),
                    "position_nodes": serializers.ListField(
                        child=serializers.DictField()
                    ),
                    "geofences": serializers.ListField(child=serializers.DictField()),
                },
            ),
        },
    )
    def get(self, request):
        facility_id = request.query_params.get("facility_id")

        facilities_qs = Facility.objects.filter(is_active=True)
        gas_qs = GasSensor.objects.filter(is_active=True)
        power_qs = PowerDevice.objects.filter(is_active=True)
        node_qs = PositionNode.objects.filter(is_active=True)
        geofence_qs = GeoFence.objects.filter(is_active=True)

        if facility_id:
            gas_qs = gas_qs.filter(facility_id=facility_id)
            power_qs = power_qs.filter(facility_id=facility_id)
            node_qs = node_qs.filter(facility_id=facility_id)
            geofence_qs = geofence_qs.filter(facility_id=facility_id)

        return Response(
            {
                "facilities": FacilityMapSerializer(facilities_qs, many=True).data,
                "gas_sensors": GasSensorMapSerializer(gas_qs, many=True).data,
                "power_devices": PowerDeviceMapSerializer(power_qs, many=True).data,
                "position_nodes": PositionNodeMapSerializer(node_qs, many=True).data,
                "geofences": GeoFenceMapSerializer(geofence_qs, many=True).data,
            }
        )


class MapEditorSaveView(APIView):
    """
    POST /api/map-editor/save/
    편집된 모든 객체의 위치/크기/지오펜스를 일괄 저장한다.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Map Editor"],
        summary="지도 편집 — 일괄 저장",
        description=(
            "편집 화면에서 변경된 객체 위치/크기/지오펜스를 하나의 트랜잭션으로 저장한다. "
            "지오펜스는 신규/기존/삭제 모두 한 번에 처리. 원형 지오펜스는 polygon으로 근사."
        ),
        request=MapEditorSaveSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="MapEditorSaveResponse",
                fields={
                    "saved": serializers.BooleanField(),
                    "updated": inline_serializer(
                        name="MapEditorSaveCounts",
                        fields={
                            "facilities": serializers.IntegerField(),
                            "gas_sensors": serializers.IntegerField(),
                            "power_devices": serializers.IntegerField(),
                            "position_nodes": serializers.IntegerField(),
                            "geofences_saved": serializers.IntegerField(),
                            "geofences_deleted": serializers.IntegerField(),
                        },
                    ),
                },
            ),
            400: OpenApiResponse(description="검증 실패"),
        },
    )
    @transaction.atomic
    def post(self, request):
        serializer = MapEditorSaveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        updated = {
            "facilities": 0,
            "gas_sensors": 0,
            "power_devices": 0,
            "position_nodes": 0,
            "geofences_saved": 0,
            "geofences_deleted": 0,
        }

        # 설비 위치/크기 저장
        for item in data["facilities"]:
            Facility.objects.filter(pk=item["id"]).update(
                map_x=item["map_x"],
                map_y=item["map_y"],
                map_width=item["map_width"],
                map_height=item["map_height"],
            )
            updated["facilities"] += 1

        # 가스 센서 위치 저장
        for item in data["gas_sensors"]:
            GasSensor.objects.filter(pk=item["id"]).update(x=item["x"], y=item["y"])
            updated["gas_sensors"] += 1

        # 전력 장치 위치 저장
        for item in data["power_devices"]:
            PowerDevice.objects.filter(pk=item["id"]).update(x=item["x"], y=item["y"])
            updated["power_devices"] += 1

        # 위치 노드 위치 저장
        for item in data["position_nodes"]:
            PositionNode.objects.filter(pk=item["id"]).update(x=item["x"], y=item["y"])
            updated["position_nodes"] += 1

        # 지오펜스 저장/삭제
        for item in data["geofences"]:
            if item.get("deleted") and item.get("id"):
                GeoFence.objects.filter(pk=item["id"]).update(is_active=False)
                updated["geofences_deleted"] += 1
                continue

            # 원형이면 polygon 근사 계산
            if item.get("shape_type") == "circle":
                cx = item.get("circle_cx", 0)
                cy = item.get("circle_cy", 0)
                r = item.get("circle_radius", 50)
                polygon = circle_to_polygon(cx, cy, r)
            else:
                polygon = item.get("polygon", [])

            if item.get("id"):
                GeoFence.objects.filter(pk=item["id"]).update(
                    name=item["name"],
                    risk_level=item["risk_level"],
                    shape_type=item.get("shape_type", "polygon"),
                    polygon=polygon,
                    circle_cx=item.get("circle_cx"),
                    circle_cy=item.get("circle_cy"),
                    circle_radius=item.get("circle_radius"),
                )
            else:
                GeoFence.objects.create(
                    facility_id=item["facility_id"],
                    name=item["name"],
                    risk_level=item["risk_level"],
                    shape_type=item.get("shape_type", "polygon"),
                    polygon=polygon,
                    circle_cx=item.get("circle_cx"),
                    circle_cy=item.get("circle_cy"),
                    circle_radius=item.get("circle_radius"),
                )
            updated["geofences_saved"] += 1

        return Response({"saved": True, "updated": updated})
