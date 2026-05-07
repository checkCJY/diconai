# Create your views here.
# apps/geofence/views.py
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny

from apps.geofence.models import GeoFence
from apps.geofence.serializers import GeoFenceSerializer
from apps.geofence.services.geofence_service import create_geofence


@extend_schema_view(
    list=extend_schema(
        tags=["Geofence"],
        summary="지오펜스 목록",
        parameters=[
            OpenApiParameter(
                name="facility_id",
                type=int,
                required=False,
                description="공장 ID 필터",
            ),
        ],
    ),
    retrieve=extend_schema(tags=["Geofence"], summary="지오펜스 상세"),
    create=extend_schema(
        tags=["Geofence"],
        summary="지오펜스 생성",
        description="다각형 좌표(`polygon`)와 위험도(`risk_level`: normal/warning/danger)로 생성.",
        examples=[
            OpenApiExample(
                "위험구역 (사각형) 생성",
                description="A공장 압연기 주변 4점 polygon",
                value={
                    "facility": 1,
                    "name": "A구역 — 압연기 주변",
                    "risk_level": "danger",
                    "polygon": [[100, 80], [300, 80], [300, 220], [100, 220]],
                    "description": "압연기 작동 중 접근 금지 구역",
                },
                request_only=True,
            ),
            OpenApiExample(
                "주의구역 (다각형) 생성",
                value={
                    "facility": 1,
                    "name": "C구역 — 컨베이어",
                    "risk_level": "warning",
                    "polygon": [
                        [600, 100],
                        [900, 100],
                        [900, 250],
                        [750, 350],
                        [600, 250],
                    ],
                    "description": "컨베이어 작업 중 주의 필요",
                },
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(tags=["Geofence"], summary="지오펜스 전체 수정"),
    partial_update=extend_schema(tags=["Geofence"], summary="지오펜스 부분 수정"),
    destroy=extend_schema(
        tags=["Geofence"],
        summary="지오펜스 삭제 (Soft Delete)",
        description="`is_active=False`로 비활성화. 실제 행은 보존.",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            204: OpenApiResponse(description="삭제 완료"),
        },
    ),
)
class GeoFenceViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    """
    GeoFence CRUD API

    GET    /api/geofences/              → 목록
    POST   /api/geofences/              → 생성
    GET    /api/geofences/{id}/         → 상세
    PUT    /api/geofences/{id}/         → 수정
    DELETE /api/geofences/{id}/         → 삭제 (Soft Delete)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = GeoFenceSerializer

    def get_queryset(self):
        """활성 지오펜스만 반환, facility_id로 필터링 가능"""
        queryset = GeoFence.objects.filter(is_active=True)
        facility_id = self.request.query_params.get("facility_id")
        if facility_id:
            queryset = queryset.filter(facility_id=facility_id)
        return queryset.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        """지오펜스 생성"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        geofence = create_geofence(
            facility_id=serializer.validated_data["facility"].id,
            name=serializer.validated_data["name"],
            polygon=serializer.validated_data["polygon"],
            risk_level=serializer.validated_data["risk_level"],
            description=serializer.validated_data.get("description", ""),
        )
        return Response(
            GeoFenceSerializer(geofence).data, status=status.HTTP_201_CREATED
        )

    def destroy(self, request, *args, **kwargs):
        """지오펜스 삭제 (Soft Delete — is_active=False)"""
        geofence = self.get_object()
        geofence.deactivate()
        return Response(
            {"detail": f'지오펜스 "{geofence.name}" 삭제 완료'},
            status=status.HTTP_204_NO_CONTENT,
        )

    @extend_schema(
        tags=["Geofence"],
        summary="공장별 지오펜스 목록",
        parameters=[OpenApiParameter(name="facility_id", type=int, required=True)],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: GeoFenceSerializer(many=True),
            400: OpenApiResponse(description="facility_id 누락"),
        },
    )
    @action(detail=False, methods=["get"])
    def by_facility(self, request):
        """공장별 지오펜스 목록 — GET /api/geofences/by-facility/?facility_id=1"""
        facility_id = request.query_params.get("facility_id")
        if not facility_id:
            return Response(
                {"detail": "facility_id 파라미터가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        geofences = self.get_queryset().filter(facility_id=facility_id)
        return Response(GeoFenceSerializer(geofences, many=True).data)
