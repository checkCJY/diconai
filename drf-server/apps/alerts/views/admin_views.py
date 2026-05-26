"""어드민 패널 — 알림 정책 관리 뷰.

URL 프리픽스: /api/admin/alerts/policies/

목록·생성·상세·수정·삭제. 매처 캐시 무효화는 [[policy_matcher.save_policy]] 가
처리하므로 view 는 호출 책임 없음 (serializer 의 create/update 가 위임).
"""

from django.db import transaction
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.models import AlertPolicy
from apps.alerts.selectors.alert_policy_admin import list_admin_policies
from apps.alerts.serializers.alert_policy_admin import (
    AlertPolicyDetailSerializer,
    AlertPolicyListSerializer,
    AlertPolicyWriteSerializer,
)
from apps.alerts.services.policy_matcher import _invalidate_policy_cache
from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdmin


def _parse_bool(value: str | None) -> bool | None:
    """쿼리 파라미터 "true"/"false"/"1"/"0" → bool. 미입력 시 None (전체)."""
    if value is None or value == "":
        return None
    return value.lower() in ("true", "1", "yes")


class AlertPolicyAdminListView(APIView):
    """GET  /api/admin/alerts/policies/  — 정책 목록 (필터·정렬·페이지네이션)
    POST /api/admin/alerts/policies/  — 정책 신규 등록

    [GET 쿼리]
    - name        : 정책명 부분검색 (icontains)
    - event_type  : AlarmType 값 (예: gas_threshold)
    - is_active   : true / false
    - sort        : updated_desc / updated_asc / name_asc / name_desc /
                   event_asc / event_desc / active_first / inactive_first
    - page, page_size : 페이지네이션
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — AlertPolicy"],
        summary="알림 정책 목록",
        parameters=[
            OpenApiParameter(name="name", type=str, required=False),
            OpenApiParameter(name="event_type", type=str, required=False),
            OpenApiParameter(name="is_active", type=str, required=False),
            OpenApiParameter(name="sort", type=str, required=False),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            200: AlertPolicyListSerializer(many=True),
            401: OpenApiResponse(description="인증 필요"),
        },
    )
    def get(self, request):
        qs = list_admin_policies(
            name=request.query_params.get("name", ""),
            event_type=request.query_params.get("event_type"),
            is_active=_parse_bool(request.query_params.get("is_active")),
            sort=request.query_params.get("sort", "updated_desc"),
        )
        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AlertPolicyListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["Admin — AlertPolicy"],
        summary="알림 정책 신규 등록",
        request=AlertPolicyWriteSerializer,
        responses={
            201: AlertPolicyDetailSerializer,
            400: OpenApiResponse(description="검증 실패"),
            401: OpenApiResponse(description="인증 필요"),
        },
    )
    @transaction.atomic
    def post(self, request):
        serializer = AlertPolicyWriteSerializer(data=request.data)
        if serializer.is_valid():
            policy = serializer.save()
            return Response(
                AlertPolicyDetailSerializer(policy).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AlertPolicyAdminDetailView(APIView):
    """GET    /api/admin/alerts/policies/<id>/  — 상세 조회 (폼 prefill)
    PATCH  /api/admin/alerts/policies/<id>/  — 정책 수정 (partial)
    DELETE /api/admin/alerts/policies/<id>/  — 정책 삭제 (Hard delete; 시연 단계)
    """

    permission_classes = [IsSuperAdmin]

    def _get_policy(self, pk: int) -> AlertPolicy | None:
        try:
            return AlertPolicy.objects.select_related("target_facility").get(pk=pk)
        except AlertPolicy.DoesNotExist:
            return None

    @extend_schema(
        tags=["Admin — AlertPolicy"],
        summary="알림 정책 상세 조회",
        responses={
            200: AlertPolicyDetailSerializer,
            404: OpenApiResponse(description="정책 없음"),
        },
    )
    def get(self, request, pk):
        policy = self._get_policy(pk)
        if not policy:
            return Response(
                {"detail": "정책을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AlertPolicyDetailSerializer(policy).data)

    @extend_schema(
        tags=["Admin — AlertPolicy"],
        summary="알림 정책 수정 (Partial)",
        request=AlertPolicyWriteSerializer,
        responses={
            200: AlertPolicyDetailSerializer,
            400: OpenApiResponse(description="검증 실패"),
            404: OpenApiResponse(description="정책 없음"),
        },
    )
    @transaction.atomic
    def patch(self, request, pk):
        policy = self._get_policy(pk)
        if not policy:
            return Response(
                {"detail": "정책을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = AlertPolicyWriteSerializer(policy, data=request.data, partial=True)
        if serializer.is_valid():
            policy = serializer.save()
            return Response(AlertPolicyDetailSerializer(policy).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["Admin — AlertPolicy"],
        summary="알림 정책 삭제",
        responses={
            204: OpenApiResponse(description="삭제 완료"),
            404: OpenApiResponse(description="정책 없음"),
        },
    )
    def delete(self, request, pk):
        policy = self._get_policy(pk)
        if not policy:
            return Response(
                {"detail": "정책을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        event_type = policy.event_type
        policy.delete()
        # 매처 캐시 무효화 — 삭제된 정책이 다음 매칭에 잡히지 않도록.
        _invalidate_policy_cache(event_type)
        return Response(status=status.HTTP_204_NO_CONTENT)
