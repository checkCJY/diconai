"""
apps/accounts/views/org_views.py
조직 관리 API 뷰
URL 프리픽스: /api/admin/
"""

from django.contrib.auth import get_user_model
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Company, Department, UserDepartment
from apps.accounts.serializers.org_serializers import (
    CompanyTreeSerializer,
    DeptCreateSerializer,
    DeptDetailSerializer,
    DeptUpdateSerializer,
    MemberListSerializer,
)
from apps.core.models.system_log import SystemLog
from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdmin

User = get_user_model()


def _log(actor, action_type, target, description="", old=None, new=None, request=None):
    ip = None
    if request:
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = (
            x_forwarded.split(",")[0].strip()
            if x_forwarded
            else request.META.get("REMOTE_ADDR")
        )
    SystemLog.objects.create(
        actor=actor,
        action_type=action_type,
        target_model=target.__class__.__name__,
        target_id=str(target.pk),
        old_value=old,
        new_value=new,
        description=description,
        ip_address=ip,
    )


# ── 조직도 트리 ────────────────────────────────────────────────────────────


class OrgTreeView(APIView):
    """
    GET /api/admin/organizations/tree/
    회사 목록과 각 회사의 부서 트리, 조직 없음 인원 수 반환.
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Organization"],
        summary="회사·부서 트리 + 조직 없음 인원 수",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="OrgTreeResponse",
                fields={
                    "companies": serializers.ListField(child=serializers.DictField()),
                    "no_dept_count": serializers.IntegerField(),
                },
            ),
        },
    )
    def get(self, request):
        companies = list(Company.objects.filter(is_active=True))
        all_depts = list(
            Department.objects.filter(is_active=True)
            .select_related("leader")
            .order_by("code")
        )
        no_dept_count = User.objects.filter(
            is_active=True, dept_memberships__isnull=True
        ).count()

        ctx = {"all_depts": all_depts}
        data = CompanyTreeSerializer(companies, many=True, context=ctx).data
        return Response({"companies": list(data), "no_dept_count": no_dept_count})


# ── 부서 목록 생성 ─────────────────────────────────────────────────────────


class DeptListCreateView(APIView):
    """
    POST /api/admin/departments/
    새 부서 생성.
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Organization"],
        summary="부서 신규 생성",
        request=DeptCreateSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            201: DeptDetailSerializer,
            400: OpenApiResponse(description="검증 실패"),
        },
    )
    def post(self, request):
        serializer = DeptCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        dept = serializer.save(updated_by=request.user)
        _log(
            actor=request.user,
            action_type=SystemLog.ActionType.DEPT_CREATE,
            target=dept,
            description=f"부서 생성: {dept.name}",
            new={"name": dept.name, "code": dept.code},
            request=request,
        )
        return Response(DeptDetailSerializer(dept).data, status=status.HTTP_201_CREATED)


# ── 부서 상세 / 수정 / 삭제 ───────────────────────────────────────────────


class DeptDetailView(APIView):
    """
    GET    /api/admin/departments/{id}/  — 부서 상세
    PATCH  /api/admin/departments/{id}/  — 부서 수정
    DELETE /api/admin/departments/{id}/  — 부서 비활성화 (소프트 삭제)
    """

    permission_classes = [IsSuperAdmin]

    def _get_dept(self, pk):
        try:
            return Department.objects.select_related(
                "company", "leader", "updated_by"
            ).get(pk=pk, is_active=True)
        except Department.DoesNotExist:
            return None

    @extend_schema(
        tags=["Admin — Organization"],
        summary="부서 상세",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: DeptDetailSerializer,
            404: OpenApiResponse(description="부서 없음"),
        },
    )
    def get(self, request, pk):
        dept = self._get_dept(pk)
        if not dept:
            return Response(
                {"error": "부서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(DeptDetailSerializer(dept).data)

    @extend_schema(
        tags=["Admin — Organization"],
        summary="부서 수정 (Partial)",
        request=DeptUpdateSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: DeptDetailSerializer,
            400: OpenApiResponse(description="검증 실패"),
            404: OpenApiResponse(description="부서 없음"),
        },
    )
    def patch(self, request, pk):
        dept = self._get_dept(pk)
        if not dept:
            return Response(
                {"error": "부서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )

        old = {"name": dept.name, "code": dept.code}
        serializer = DeptUpdateSerializer(dept, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        dept = serializer.save(updated_by=request.user)
        _log(
            actor=request.user,
            action_type=SystemLog.ActionType.DEPT_UPDATE,
            target=dept,
            description=f"부서 수정: {dept.name}",
            old=old,
            new={"name": dept.name, "code": dept.code},
            request=request,
        )
        return Response(DeptDetailSerializer(dept).data)

    @extend_schema(
        tags=["Admin — Organization"],
        summary="부서 비활성화 (Soft Delete)",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            204: OpenApiResponse(description="삭제 완료"),
            404: OpenApiResponse(description="부서 없음"),
        },
    )
    def delete(self, request, pk):
        dept = self._get_dept(pk)
        if not dept:
            return Response(
                {"error": "부서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )

        dept.is_active = False
        dept.updated_by = request.user
        dept.save(update_fields=["is_active", "updated_by", "updated_at"])

        _log(
            actor=request.user,
            action_type=SystemLog.ActionType.DEPT_DELETE,
            target=dept,
            description=f"부서 삭제: {dept.name}",
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 구성원 목록 ────────────────────────────────────────────────────────────


class DeptMemberListView(APIView):
    """
    GET /api/admin/departments/{id}/members/
    GET /api/admin/departments/none/members/   ← 조직 없음
    쿼리: q(이름/ID 검색), page, page_size
    조직장이 항상 최상단에 위치.
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Organization"],
        summary="부서 구성원 목록",
        description=(
            "조직장이 항상 최상단. `pk='none'`이면 어디 부서에도 속하지 않은 사용자 목록 반환."
        ),
        parameters=[
            OpenApiParameter(
                name="q", type=str, required=False, description="이름/ID 검색"
            ),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: MemberListSerializer(many=True),
            404: OpenApiResponse(description="부서 없음"),
        },
    )
    def get(self, request, pk):
        is_no_dept = str(pk) == "none"

        if is_no_dept:
            qs = User.objects.filter(
                is_active=True,
                dept_memberships__isnull=True,
            ).select_related("position")
            dept_id = None
        else:
            try:
                dept = Department.objects.get(pk=pk, is_active=True)
            except Department.DoesNotExist:
                return Response(
                    {"error": "부서를 찾을 수 없습니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            qs = User.objects.filter(
                dept_memberships__department_id=pk,
                is_active=True,
            ).select_related("position")
            dept_id = dept.id

        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(username__icontains=q)

        # 조직장 최상단 정렬
        if dept_id:
            from django.db.models import Case, When, IntegerField

            qs = qs.annotate(
                is_leader_order=Case(
                    When(leading_departments__id=dept_id, then=0),
                    default=1,
                    output_field=IntegerField(),
                )
            ).order_by("is_leader_order", "name")
        else:
            qs = qs.order_by("name")

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = MemberListSerializer(page, many=True, context={"dept_id": dept_id})
        return paginator.get_paginated_response(serializer.data)


# ── 구성원 추가 ────────────────────────────────────────────────────────────


class DeptMemberAddView(APIView):
    """
    POST /api/admin/departments/{id}/members/add/
    Body: { user_ids: [1,2,3], keep_previous: bool }
    keep_previous=true → 이전 소속 유지(겸직), false → 주소속 변경
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Organization"],
        summary="부서 구성원 추가",
        description="`keep_previous=true`면 이전 소속 유지(겸직), false면 주소속 변경.",
        request=inline_serializer(
            name="DeptMemberAddRequest",
            fields={
                "user_ids": serializers.ListField(child=serializers.IntegerField()),
                "keep_previous": serializers.BooleanField(default=False),
            },
        ),
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="DeptMemberAddResponse",
                fields={
                    "ok": serializers.BooleanField(),
                    "added": serializers.IntegerField(),
                },
            ),
            400: OpenApiResponse(description="user_ids 누락"),
            404: OpenApiResponse(description="부서 없음"),
        },
    )
    def post(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk, is_active=True)
        except Department.DoesNotExist:
            return Response(
                {"error": "부서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )

        user_ids = request.data.get("user_ids", [])
        keep_previous = request.data.get("keep_previous", False)

        if not user_ids:
            return Response(
                {"error": "user_ids가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        users = User.objects.filter(pk__in=user_ids, is_active=True)

        for user in users:
            if not keep_previous:
                # 기존 주소속 해제 후 새 부서를 주소속으로
                UserDepartment.objects.filter(user=user, is_primary=True).update(
                    is_primary=False
                )
                UserDepartment.objects.update_or_create(
                    user=user,
                    department=dept,
                    defaults={"is_primary": True},
                )
            else:
                # 겸직: 기존 유지 + 새 부서 추가(비주소속)
                UserDepartment.objects.get_or_create(
                    user=user,
                    department=dept,
                    defaults={"is_primary": False},
                )

            _log(
                actor=request.user,
                action_type=SystemLog.ActionType.MEMBER_ADD,
                target=user,
                description=f"구성원 추가: {user.name} → {dept.name}",
                new={"dept_id": dept.id, "keep_previous": keep_previous},
                request=request,
            )

        return Response({"ok": True, "added": len(users)})


# ── 부서 이동 ──────────────────────────────────────────────────────────────


class DeptMemberMoveView(APIView):
    """
    POST /api/admin/departments/{id}/members/move/
    Body: { user_ids: [1,2,3], target_dept_id: 5, keep_previous: bool }
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Organization"],
        summary="부서 구성원 이동",
        request=inline_serializer(
            name="DeptMemberMoveRequest",
            fields={
                "user_ids": serializers.ListField(child=serializers.IntegerField()),
                "target_dept_id": serializers.IntegerField(),
                "keep_previous": serializers.BooleanField(default=False),
            },
        ),
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="DeptMemberMoveResponse",
                fields={
                    "ok": serializers.BooleanField(),
                    "moved": serializers.IntegerField(),
                },
            ),
            400: OpenApiResponse(description="필수 필드 누락"),
            404: OpenApiResponse(description="대상 부서 없음"),
        },
    )
    def post(self, request, pk):
        user_ids = request.data.get("user_ids", [])
        target_dept_id = request.data.get("target_dept_id")
        keep_previous = request.data.get("keep_previous", False)

        if not user_ids or not target_dept_id:
            return Response(
                {"error": "user_ids와 target_dept_id가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_dept = Department.objects.get(pk=target_dept_id, is_active=True)
        except Department.DoesNotExist:
            return Response(
                {"error": "대상 부서를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        users = User.objects.filter(pk__in=user_ids, is_active=True)

        for user in users:
            if not keep_previous:
                UserDepartment.objects.filter(user=user, is_primary=True).update(
                    is_primary=False
                )
                UserDepartment.objects.update_or_create(
                    user=user,
                    department=target_dept,
                    defaults={"is_primary": True},
                )
            else:
                UserDepartment.objects.get_or_create(
                    user=user,
                    department=target_dept,
                    defaults={"is_primary": False},
                )

            _log(
                actor=request.user,
                action_type=SystemLog.ActionType.MEMBER_MOVE,
                target=user,
                description=f"부서 이동: {user.name} → {target_dept.name}",
                new={"target_dept_id": target_dept_id, "keep_previous": keep_previous},
                request=request,
            )

        return Response({"ok": True, "moved": len(users)})


# ── 소속 제외 ──────────────────────────────────────────────────────────────


class DeptMemberRemoveView(APIView):
    """
    POST /api/admin/departments/{id}/members/remove/
    Body: { user_ids: [1,2,3] }
    → 해당 부서에서 제외 (UserDepartment 삭제). 다른 소속 없으면 조직 없음 상태.
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Organization"],
        summary="부서에서 구성원 제외",
        description="해당 부서에서만 제외(UserDepartment 삭제). 다른 소속 없으면 '조직 없음' 상태.",
        request=inline_serializer(
            name="DeptMemberRemoveRequest",
            fields={
                "user_ids": serializers.ListField(child=serializers.IntegerField())
            },
        ),
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="DeptMemberRemoveResponse",
                fields={
                    "ok": serializers.BooleanField(),
                    "removed": serializers.IntegerField(),
                },
            ),
            400: OpenApiResponse(description="user_ids 누락"),
            404: OpenApiResponse(description="부서 없음"),
        },
    )
    def post(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk, is_active=True)
        except Department.DoesNotExist:
            return Response(
                {"error": "부서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )

        user_ids = request.data.get("user_ids", [])
        if not user_ids:
            return Response(
                {"error": "user_ids가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        removed = UserDepartment.objects.filter(user_id__in=user_ids, department=dept)
        count = removed.count()
        removed.delete()

        for uid in user_ids:
            try:
                user = User.objects.get(pk=uid)
                _log(
                    actor=request.user,
                    action_type=SystemLog.ActionType.MEMBER_REMOVE,
                    target=user,
                    description=f"소속 제외: {user.name} ← {dept.name}",
                    request=request,
                )
            except User.DoesNotExist:
                pass

        return Response({"ok": True, "removed": count})


# ── 조직장 임명 ────────────────────────────────────────────────────────────


class DeptLeaderAssignView(APIView):
    """
    POST /api/admin/departments/{id}/members/assign-leader/
    Body: { user_id: 1 }
    단일 사용자만 허용. 해당 부서의 leader FK를 업데이트.
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Organization"],
        summary="부서 조직장 임명",
        description="단일 사용자만 허용. 부서의 leader FK를 업데이트하고 SystemLog에 이력 기록.",
        request=inline_serializer(
            name="DeptLeaderAssignRequest",
            fields={"user_id": serializers.IntegerField()},
        ),
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="DeptLeaderAssignResponse",
                fields={
                    "ok": serializers.BooleanField(),
                    "leader": inline_serializer(
                        name="DeptLeaderInfo",
                        fields={
                            "id": serializers.IntegerField(),
                            "name": serializers.CharField(),
                        },
                    ),
                },
            ),
            400: OpenApiResponse(description="user_id 누락"),
            404: OpenApiResponse(description="부서/사용자 없음"),
        },
    )
    def post(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk, is_active=True)
        except Department.DoesNotExist:
            return Response(
                {"error": "부서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )

        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"error": "user_id가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return Response(
                {"error": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        old_leader = dept.leader
        dept.leader = user
        dept.updated_by = request.user
        dept.save(update_fields=["leader", "updated_by", "updated_at"])

        _log(
            actor=request.user,
            action_type=SystemLog.ActionType.LEADER_ASSIGN,
            target=dept,
            description=f"조직장 임명: {user.name} → {dept.name}",
            old={"leader_id": old_leader.id if old_leader else None},
            new={"leader_id": user.id},
            request=request,
        )
        return Response({"ok": True, "leader": {"id": user.id, "name": user.name}})
