# apps/geofence/views/admin_views.py
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
from django.shortcuts import get_object_or_404

from apps.geofence.models import GeoFence
from apps.geofence.serializers.admin_serializers import GeoFenceAdminSerializer

from django.views.generic import TemplateView


class GeoFenceAdminPageView(TemplateView):
    template_name = "admin_panel/geofence/geofence_list.html"
    extra_context = {"active_nav": "geofence"}


class GeoFenceAdminListView(APIView):
    """
    관리자 지오펜스 목록 조회 / 등록
    GET  /api/admin/geofences/
    POST /api/admin/geofences/
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Admin — Geofence"],
        summary="(관리자) 지오펜스 목록",
        description="검색 + 필터. `/api/geofences/` ViewSet의 어드민 버전.",
        parameters=[
            OpenApiParameter(name="facility_id", type=int, required=False),
            OpenApiParameter(
                name="name", type=str, required=False, description="이름 부분검색"
            ),
            OpenApiParameter(
                name="risk_level",
                type=str,
                required=False,
                description="normal/warning/danger",
            ),
        ],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="GeoFenceAdminListResponse",
                fields={
                    "results": GeoFenceAdminSerializer(many=True),
                    "total": serializers.IntegerField(),
                },
            ),
        },
    )
    def get(self, request):
        facility_id = request.query_params.get("facility_id")
        name = request.query_params.get("name")
        risk_level = request.query_params.get("risk_level")

        qs = GeoFence.objects.filter(is_active=True)
        if facility_id:
            qs = qs.filter(facility_id=facility_id)
        if name:
            qs = qs.filter(name__icontains=name)
        if risk_level:
            qs = qs.filter(risk_level=risk_level)

        serializer = GeoFenceAdminSerializer(qs, many=True)
        return Response({"results": serializer.data, "total": qs.count()})

    @extend_schema(
        tags=["Admin — Geofence"],
        summary="(관리자) 지오펜스 생성",
        request=GeoFenceAdminSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            201: GeoFenceAdminSerializer,
            400: OpenApiResponse(description="검증 실패"),
        },
    )
    def post(self, request):
        serializer = GeoFenceAdminSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GeoFenceAdminDetailView(APIView):
    """
    관리자 지오펜스 상세 조회 / 수정 / 삭제
    GET    /api/admin/geofences/<id>/
    PUT    /api/admin/geofences/<id>/
    DELETE /api/admin/geofences/<id>/
    """

    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(GeoFence, pk=pk, is_active=True)

    @extend_schema(
        tags=["Admin — Geofence"],
        summary="(관리자) 지오펜스 상세",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: GeoFenceAdminSerializer,
            404: OpenApiResponse(description="없음"),
        },
    )
    def get(self, request, pk):
        fence = self.get_object(pk)
        serializer = GeoFenceAdminSerializer(fence)
        return Response(serializer.data)

    @extend_schema(
        tags=["Admin — Geofence"],
        summary="(관리자) 지오펜스 수정 (Partial)",
        request=GeoFenceAdminSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: GeoFenceAdminSerializer,
            400: OpenApiResponse(description="검증 실패"),
            404: OpenApiResponse(description="없음"),
        },
    )
    def put(self, request, pk):
        fence = self.get_object(pk)
        serializer = GeoFenceAdminSerializer(fence, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["Admin — Geofence"],
        summary="(관리자) 지오펜스 비활성화 (Soft Delete)",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            204: OpenApiResponse(description="삭제 완료"),
            404: OpenApiResponse(description="없음"),
        },
    )
    def delete(self, request, pk):
        fence = self.get_object(pk)
        fence.is_active = False
        fence.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)
