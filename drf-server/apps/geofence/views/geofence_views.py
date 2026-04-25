# Create your views here.
# apps/geofence/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny

from apps.geofence.models import GeoFence
from apps.geofence.serializers import GeoFenceSerializer
from apps.geofence.services.geofence_service import create_geofence


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
