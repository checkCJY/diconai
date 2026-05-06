"""
apps/accounts/views/admin_views.py

어드민 패널 — 사용자 관리 API 뷰 모음.
사용자 목록 조회/등록, 상세 수정/비활성화, 계정 잠금/해제를 처리한다.

URL 프리픽스: /api/admin/accounts/
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.selectors.admin_users import list_admin_users
from apps.accounts.serializers import (
    AccountsAdminCreateSerializer,
    AccountsAdminDetailSerializer,
    AccountsAdminListSerializer,
    AccountsAdminUpdateSerializer,
)
from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdmin

User = get_user_model()


class AccountsAdminListView(APIView):
    """
    GET  /api/admin/accounts/  — 사용자 목록 조회
    POST /api/admin/accounts/  — 사용자 신규 등록

    [GET 쿼리 파라미터]
    - name       : 이름 부분 검색 (icontains)
    - department : 부서 ID
    - position   : 직급 ID
    - user_type  : 권한 (super_admin / facility_admin / worker / viewer)
    - status     : 계정 상태 (active / locked / inactive)
    - sort       : 정렬 (name_asc / name_desc / date_asc / date_desc)
    - page       : 페이지 번호 (기본 1)
    - page_size  : 페이지 크기 (기본 10, 최대 100)
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Accounts"],
        summary="사용자 목록",
        parameters=[
            OpenApiParameter(
                name="name", type=str, required=False, description="이름 부분검색"
            ),
            OpenApiParameter(name="department", type=int, required=False),
            OpenApiParameter(name="position", type=int, required=False),
            OpenApiParameter(
                name="user_type",
                type=str,
                required=False,
                description="super_admin/facility_admin/worker/viewer",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                required=False,
                description="active/locked/inactive",
            ),
            OpenApiParameter(
                name="sort",
                type=str,
                required=False,
                description="name_asc/name_desc/date_asc/date_desc",
            ),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: AccountsAdminListSerializer(many=True),
        },
    )
    def get(self, request):
        qs = list_admin_users(
            name=request.query_params.get("name", ""),
            department_id=request.query_params.get("department"),
            position_id=request.query_params.get("position"),
            user_type=request.query_params.get("user_type"),
            account_status=request.query_params.get("status"),
            sort=request.query_params.get("sort", "name_asc"),
        )
        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AccountsAdminListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["Admin — Accounts"],
        summary="사용자 신규 등록",
        request=AccountsAdminCreateSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            201: AccountsAdminCreateSerializer,
            400: OpenApiResponse(description="검증 실패"),
        },
    )
    @transaction.atomic
    def post(self, request):
        """새 사용자를 등록한다. 비밀번호는 해시 처리 후 저장."""
        serializer = AccountsAdminCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AccountsAdminDetailView(APIView):
    """
    GET    /api/admin/accounts/<id>/  — 사용자 상세 조회
    PATCH  /api/admin/accounts/<id>/  — 사용자 정보 수정 (비밀번호 제외)
    DELETE /api/admin/accounts/<id>/  — 사용자 비활성화 (소프트 삭제)
    """

    permission_classes = [IsSuperAdmin]

    def _get_user(self, pk):
        try:
            return (
                User.objects.prefetch_related("dept_memberships__department")
                .select_related("position")
                .get(pk=pk)
            )
        except User.DoesNotExist:
            return None

    @extend_schema(
        tags=["Admin — Accounts"],
        summary="사용자 상세 조회",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: AccountsAdminDetailSerializer,
            404: OpenApiResponse(description="사용자 없음"),
        },
    )
    def get(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response(
                {"detail": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AccountsAdminDetailSerializer(user).data)

    @extend_schema(
        tags=["Admin — Accounts"],
        summary="사용자 정보 수정 (Partial, 비밀번호 제외)",
        request=AccountsAdminUpdateSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: AccountsAdminListSerializer,
            400: OpenApiResponse(description="검증 실패"),
            404: OpenApiResponse(description="사용자 없음"),
        },
    )
    @transaction.atomic
    def patch(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response(
                {"detail": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = AccountsAdminUpdateSerializer(
            user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(AccountsAdminListSerializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["Admin — Accounts"],
        summary="사용자 비활성화 (Soft Delete)",
        description="본인 계정은 비활성화 불가.",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            204: OpenApiResponse(description="삭제 완료"),
            400: OpenApiResponse(description="본인 계정"),
            404: OpenApiResponse(description="사용자 없음"),
        },
    )
    def delete(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response(
                {"detail": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if user.pk == request.user.pk:
            return Response(
                {"detail": "본인 계정은 비활성화할 수 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.deactivate()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AccountsAdminLockView(APIView):
    """
    POST /api/admin/accounts/<id>/lock/    — 계정 잠금 (관리자 수동, 사실상 무기한)
    POST /api/admin/accounts/<id>/unlock/  — 계정 잠금 해제 및 실패 카운터 초기화

    URL의 <action> 슬러그(lock / unlock)로 동작을 구분한다.
    비활성(is_active=False) 계정에는 적용 불가.
    """

    permission_classes = [IsSuperAdmin]

    def _get_user(self, pk):
        try:
            return User.objects.get(pk=pk, is_active=True)
        except User.DoesNotExist:
            return None

    @extend_schema(
        tags=["Admin — Accounts"],
        summary="계정 잠금 / 잠금해제",
        description=(
            "URL의 `<action>` path parameter로 동작 구분 — `lock` 또는 `unlock`. "
            "잠금 시 100년 뒤로 `account_locked_until` 설정. 잠금해제 시 실패 카운터도 초기화."
        ),
        request=None,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="AccountLockResponse", fields={"ok": serializers.BooleanField()}
            ),
            400: OpenApiResponse(description="잘못된 action 값"),
            404: OpenApiResponse(description="사용자 없음"),
        },
    )
    def post(self, request, pk, action):
        user = self._get_user(pk)
        if not user:
            return Response(
                {"detail": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if action == "lock":
            # 관리자 수동 잠금 — 100년 뒤로 설정해 사실상 무기한 처리
            user.account_locked_until = timezone.now() + timezone.timedelta(days=36500)
            user.save(update_fields=["account_locked_until", "updated_at"])
        elif action == "unlock":
            # 잠금 해제 시 실패 카운터도 함께 초기화
            user.account_locked_until = None
            user.failed_login_count = 0
            user.save(
                update_fields=[
                    "account_locked_until",
                    "failed_login_count",
                    "updated_at",
                ]
            )
        else:
            return Response(
                {"detail": "잘못된 요청입니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"ok": True})
