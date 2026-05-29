"""core/views/risk_standard_admin.py

위험 기준 관리 어드민 API 뷰.
URL 프리픽스: /api/admin/risk-standards/

RiskLevelStandard 는 3개 고정 레코드 — 생성·삭제 없음, 수정만 허용.
code 필드는 읽기 전용 (RiskLevel enum 과 1:1 동기화 정책).
"""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models.risk_level_standard import RiskLevelStandard
from apps.core.permissions import IsSuperAdmin
from apps.core.serializers.risk_standard_serializers import (
    RiskStandardListSerializer,
    RiskStandardUpdateSerializer,
)


class RiskStandardAdminListView(APIView):
    """GET /api/admin/risk-standards/ — 위험 기준 목록.

    [쿼리 파라미터]
    - code        : 단계코드 (normal / warning / danger)
    - is_active   : true / false
    - display_color : 색상 토큰 문자열 (부분 일치)
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — RiskStandard"],
        summary="위험 기준 목록",
        parameters=[
            OpenApiParameter(name="code", type=str, required=False),
            OpenApiParameter(name="is_active", type=str, required=False),
            OpenApiParameter(name="display_color", type=str, required=False),
        ],
        responses={200: RiskStandardListSerializer(many=True)},
    )
    def get(self, request):
        qs = RiskLevelStandard.objects.order_by("event_priority")

        # 단계코드 필터
        code = request.query_params.get("code")
        if code:
            qs = qs.filter(code=code)

        # 사용여부 필터 — "true"/"false" 문자열 → bool
        is_active = request.query_params.get("is_active")
        if is_active is not None and is_active != "":
            qs = qs.filter(is_active=is_active.lower() in ("true", "1"))

        # 색상 필터 (부분 일치)
        display_color = request.query_params.get("display_color")
        if display_color:
            qs = qs.filter(display_color__icontains=display_color)

        serializer = RiskStandardListSerializer(qs, many=True)
        return Response(serializer.data)


class RiskStandardAdminDetailView(APIView):
    """PATCH /api/admin/risk-standards/<id>/ — 위험 기준 수정.

    code 필드를 제외한 나머지 필드만 수정 가능.
    """

    permission_classes = [IsSuperAdmin]

    def _get_obj(self, pk):
        try:
            return RiskLevelStandard.objects.get(pk=pk)
        except RiskLevelStandard.DoesNotExist:
            return None

    @extend_schema(
        tags=["Admin — RiskStandard"],
        summary="위험 기준 수정",
        request=RiskStandardUpdateSerializer,
        responses={
            200: RiskStandardListSerializer,
            400: OpenApiResponse(description="검증 실패"),
            404: OpenApiResponse(description="항목 없음"),
        },
    )
    def patch(self, request, pk):
        obj = self._get_obj(pk)
        if not obj:
            return Response(
                {"detail": "위험 기준을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = RiskStandardUpdateSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        obj = serializer.save()
        # 응답은 전체 필드를 반환 (JS 에서 행 갱신에 사용)
        return Response(RiskStandardListSerializer(obj).data)
