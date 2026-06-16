"""facilities/views/threshold_admin.py

임계치 기준 관리 어드민 API 뷰.

[URL 구조]
GET/POST   /api/admin/threshold-groups/          — 그룹 목록 / 그룹 생성
PATCH/DEL  /api/admin/threshold-groups/<id>/     — 그룹 수정 / 그룹 삭제
GET/POST   /api/admin/threshold-groups/<id>/thresholds/  — 임계치 목록 / 생성
PATCH/DEL  /api/admin/thresholds/<id>/           — 임계치 수정 / 삭제

[facility 정책]
임계치 항목은 facility=null (전사 기준)만 관리.
공장별 예외 기준은 Phase 2 이후 별도 범위로 진행.
"""

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsSuperAdmin
from apps.facilities.models.thresholds import Threshold, ThresholdGroup
from apps.facilities.serializers.threshold_admin import (
    ThresholdGroupSerializer,
    ThresholdGroupWriteSerializer,
    ThresholdSerializer,
    ThresholdWriteSerializer,
)

_TAG = "Admin — 임계치"


class ThresholdGroupAdminListView(APIView):
    """GET  /api/admin/threshold-groups/ — 그룹 목록 (이름/코드 검색 지원)
    POST /api/admin/threshold-groups/ — 그룹 생성
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=[_TAG],
        summary="임계치 그룹 목록",
        parameters=[
            OpenApiParameter("q", str, description="그룹명 또는 그룹코드 부분 검색"),
        ],
        responses=ThresholdGroupSerializer(many=True),
    )
    def get(self, request):
        qs = ThresholdGroup.objects.all()

        # 이름 또는 코드 부분 검색
        q = request.query_params.get("q")
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)

        serializer = ThresholdGroupSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=[_TAG],
        summary="임계치 그룹 생성",
        request=ThresholdGroupWriteSerializer,
        responses={201: ThresholdGroupSerializer},
    )
    def post(self, request):
        serializer = ThresholdGroupWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        group = serializer.save()
        return Response(
            ThresholdGroupSerializer(group).data,
            status=status.HTTP_201_CREATED,
        )


class ThresholdGroupAdminDetailView(APIView):
    """PATCH  /api/admin/threshold-groups/<id>/ — 그룹 수정
    DELETE /api/admin/threshold-groups/<id>/ — 그룹 삭제

    삭제 시 PROTECT 제약 — 하위 Threshold 가 있으면 400 반환.
    """

    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        try:
            return ThresholdGroup.objects.get(pk=pk)
        except ThresholdGroup.DoesNotExist:
            return None

    @extend_schema(
        tags=[_TAG],
        summary="임계치 그룹 수정",
        request=ThresholdGroupWriteSerializer,
        responses={
            200: ThresholdGroupSerializer,
            404: OpenApiResponse(description="그룹을 찾을 수 없음"),
        },
    )
    def patch(self, request, pk):
        group = self._get(pk)
        if not group:
            return Response(
                {"detail": "그룹을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = ThresholdGroupWriteSerializer(
            group, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        group = serializer.save()
        return Response(ThresholdGroupSerializer(group).data)

    @extend_schema(
        tags=[_TAG],
        summary="임계치 그룹 삭제",
        responses={
            204: OpenApiResponse(description="삭제 성공"),
            400: OpenApiResponse(description="하위 임계치가 있어 삭제 불가"),
            404: OpenApiResponse(description="그룹을 찾을 수 없음"),
        },
    )
    def delete(self, request, pk):
        group = self._get(pk)
        if not group:
            return Response(
                {"detail": "그룹을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )

        # 하위 임계치가 있으면 삭제 차단 (PROTECT 정책 반영)
        if group.thresholds.exists():
            return Response(
                {
                    "detail": "임계치 항목이 있는 그룹은 삭제할 수 없습니다. 먼저 임계치를 모두 삭제하세요."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ThresholdAdminListView(APIView):
    """GET  /api/admin/threshold-groups/<group_id>/thresholds/ — 임계치 목록
    POST /api/admin/threshold-groups/<group_id>/thresholds/ — 임계치 생성

    facility=null (전사 기준)만 조회·생성.
    """

    permission_classes = [IsSuperAdmin]

    def _get_group(self, group_id):
        try:
            return ThresholdGroup.objects.get(pk=group_id)
        except ThresholdGroup.DoesNotExist:
            return None

    @extend_schema(
        tags=[_TAG],
        summary="임계치 목록 (전사 기준)",
        responses={
            200: ThresholdSerializer(many=True),
            404: OpenApiResponse(description="그룹을 찾을 수 없음"),
        },
    )
    def get(self, request, group_id):
        group = self._get_group(group_id)
        if not group:
            return Response(
                {"detail": "그룹을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )

        # facility=null 전사 기준만 반환
        qs = Threshold.objects.filter(group=group, facility__isnull=True)
        serializer = ThresholdSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=[_TAG],
        summary="임계치 생성 (전사 기준)",
        request=ThresholdWriteSerializer,
        responses={
            201: ThresholdSerializer,
            404: OpenApiResponse(description="그룹을 찾을 수 없음"),
        },
    )
    def post(self, request, group_id):
        group = self._get_group(group_id)
        if not group:
            return Response(
                {"detail": "그룹을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = ThresholdWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # facility=null 고정으로 저장 (전사 기준)
        threshold = serializer.save(group=group, facility=None)
        return Response(
            ThresholdSerializer(threshold).data, status=status.HTTP_201_CREATED
        )


class ThresholdAdminDetailView(APIView):
    """PATCH  /api/admin/thresholds/<id>/ — 임계치 수정
    DELETE /api/admin/thresholds/<id>/ — 임계치 삭제
    """

    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        try:
            return Threshold.objects.get(pk=pk)
        except Threshold.DoesNotExist:
            return None

    @extend_schema(
        tags=[_TAG],
        summary="임계치 수정",
        request=ThresholdWriteSerializer,
        responses={
            200: ThresholdSerializer,
            404: OpenApiResponse(description="임계치를 찾을 수 없음"),
        },
    )
    def patch(self, request, pk):
        threshold = self._get(pk)
        if not threshold:
            return Response(
                {"detail": "임계치를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ThresholdWriteSerializer(
            threshold, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        threshold = serializer.save()
        return Response(ThresholdSerializer(threshold).data)

    @extend_schema(
        tags=[_TAG],
        summary="임계치 삭제",
        responses={
            204: OpenApiResponse(description="삭제 성공"),
            404: OpenApiResponse(description="임계치를 찾을 수 없음"),
        },
    )
    def delete(self, request, pk):
        threshold = self._get(pk)
        if not threshold:
            return Response(
                {"detail": "임계치를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        threshold.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ThresholdBulkDeactivateView(APIView):
    """POST /api/admin/thresholds/bulk-deactivate/

    선택된 임계치 항목들을 일괄 미사용으로 전환한다.
    body: { "ids": [1, 2, 3] }
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=[_TAG],
        summary="임계치 일괄 미사용 전환",
        request=inline_serializer(
            name="ThresholdBulkDeactivateRequest",
            fields={"ids": serializers.ListField(child=serializers.IntegerField())},
        ),
        responses=inline_serializer(
            name="ThresholdBulkDeactivateResponse",
            fields={"updated": serializers.IntegerField()},
        ),
    )
    def post(self, request):
        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "ids 목록이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        updated = Threshold.objects.filter(pk__in=ids).update(is_active=False)
        return Response({"updated": updated})
