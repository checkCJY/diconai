"""
apps/accounts/views/admin_views.py

어드민 패널 — 사용자 관리 API 뷰 모음.
사용자 목록 조회/등록, 상세 수정/비활성화, 계정 잠금/해제를 처리한다.

URL 프리픽스: /api/admin/accounts/
"""

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsSuperAdmin
from apps.accounts.serializers import (
    AccountsAdminCreateSerializer,
    AccountsAdminDetailSerializer,
    AccountsAdminListSerializer,
    AccountsAdminUpdateSerializer,
)
from apps.core.pagination import AdminPagination

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

    def get(self, request):
        """필터·정렬·페이지네이션이 적용된 사용자 목록을 반환한다."""
        qs = (
            User.objects.prefetch_related("dept_memberships__department")
            .select_related("position")
            .all()
        )

        name = request.query_params.get("name", "").strip()
        department_id = request.query_params.get("department")
        position_id = request.query_params.get("position")
        user_type = request.query_params.get("user_type")
        account_status = request.query_params.get("status")
        sort = request.query_params.get("sort", "name_asc")

        if name:
            qs = qs.filter(name__icontains=name)
        if department_id:
            qs = qs.filter(
                dept_memberships__department_id=department_id,
                dept_memberships__is_primary=True,
            )
        if position_id:
            qs = qs.filter(position_id=position_id)
        if user_type:
            qs = qs.filter(user_type=user_type)

        # 계정 상태 필터 — is_active + account_locked_until 조합으로 판별
        if account_status == "active":
            qs = qs.filter(is_active=True, account_locked_until=None)
        elif account_status == "locked":
            qs = qs.filter(is_active=True, account_locked_until__gt=timezone.now())
        elif account_status == "inactive":
            qs = qs.filter(is_active=False)

        sort_map = {
            "name_asc": "name",
            "name_desc": "-name",
            "date_asc": "date_joined",
            "date_desc": "-date_joined",
        }
        qs = qs.order_by(sort_map.get(sort, "name"))

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AccountsAdminListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

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

    ※ DELETE는 실제 DB 레코드를 삭제하지 않는다.
       CustomUser.deactivate()를 호출해 is_active=False 처리한다.
    """

    permission_classes = [IsSuperAdmin]

    def _get_user(self, pk):
        """pk로 사용자를 조회한다. 없으면 None 반환."""
        try:
            return (
                User.objects.prefetch_related("dept_memberships__department")
                .select_related("position")
                .get(pk=pk)
            )
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        """단일 사용자 상세 정보를 반환한다."""
        user = self._get_user(pk)
        if not user:
            return Response(
                {"error": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AccountsAdminDetailSerializer(user).data)

    def patch(self, request, pk):
        """사용자 정보(이름·부서·직급·권한·연락처)를 부분 수정한다."""
        user = self._get_user(pk)
        if not user:
            return Response(
                {"error": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = AccountsAdminUpdateSerializer(
            user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(AccountsAdminListSerializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """사용자를 비활성화한다. 본인 계정은 비활성화 불가."""
        user = self._get_user(pk)
        if not user:
            return Response(
                {"error": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if user.pk == request.user.pk:
            return Response(
                {"error": "본인 계정은 비활성화할 수 없습니다."},
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
        """활성 사용자만 조회한다. 비활성이면 None 반환."""
        try:
            return User.objects.get(pk=pk, is_active=True)
        except User.DoesNotExist:
            return None

    def post(self, request, pk, action):
        """action 값에 따라 잠금 또는 잠금 해제를 수행한다."""
        user = self._get_user(pk)
        if not user:
            return Response(
                {"error": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if action == "lock":
            # 관리자 수동 잠금 — account_locked_until을 100년 뒤로 설정해 사실상 무기한 처리
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
                {"error": "잘못된 요청입니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"ok": True})
