"""
apps/accounts/views/auth_views.py

인증 관련 API 뷰 모음.
로그인, 로그아웃, 내 정보 조회, 비밀번호 변경 등
일반 사용자(비관리자 포함)가 사용하는 인증 흐름을 처리한다.

URL 프리픽스: /api/auth/
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models.login_log import LoginLog
from apps.accounts.serializers import (
    LoginSerializer,
    MyProfileSerializer,
    PasswordChangeSerializer,
)
from apps.dashboard.menu import get_menu_tree


def _get_client_ip(request):
    """X-Forwarded-For 헤더 우선, 없으면 REMOTE_ADDR 반환."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class LoginView(APIView):
    """
    POST /api/auth/login/

    아이디/비밀번호 인증 후 JWT(access + refresh) 발급.
    - 계정 잠금·비활성 상태 사전 검사
    - 실패 시 LoginLog 기록, 성공 시 실패 카운터 초기화
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="로그인 (JWT 발급)",
        description=(
            "아이디/비밀번호로 인증 후 JWT access + refresh 토큰을 발급한다. "
            "계정 잠금 상태이거나 비활성 사용자면 인증 실패로 처리되며 LoginLog에 기록된다."
        ),
        request=LoginSerializer,
        responses={
            200: inline_serializer(
                name="LoginSuccess",
                fields={
                    "access": serializers.CharField(),
                    "refresh": serializers.CharField(),
                    "username": serializers.CharField(),
                    "role": serializers.CharField(
                        help_text="worker / facility_admin / super_admin / viewer"
                    ),
                },
            ),
            400: OpenApiResponse(
                description="필드 검증 실패 (username/password 누락 등)"
            ),
            401: OpenApiResponse(
                description="인증 실패 (비밀번호 불일치 / 계정 잠금 / 비활성)"
            ),
        },
        examples=[
            OpenApiExample(
                "정상 로그인 요청",
                value={"username": "admin", "password": "yourpassword"},
                request_only=True,
            ),
            OpenApiExample(
                "정상 로그인 응답",
                value={
                    "access": "eyJhbGciOiJIUzI1NiIs...",
                    "refresh": "eyJhbGciOiJIUzI1NiIs...",
                    "username": "admin",
                    "role": "super_admin",
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "인증 실패 응답",
                value={"error": "비밀번호가 일치하지 않습니다."},
                response_only=True,
                status_codes=["401"],
            ),
        ],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})

        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]

        if not serializer.is_valid():
            errors = serializer.errors

            # 인증 단계 실패(non_field_errors)일 때만 LoginLog 기록
            # 포맷 오류(username/password 필드 에러)는 로그 대상 아님
            if "non_field_errors" in errors:
                failure_type = getattr(
                    serializer, "_login_failure", LoginLog.LoginResult.FAILED_PASSWORD
                )
                username = request.data.get("username", "")
                try:
                    user_obj = (
                        get_user_model().objects.filter(username=username).first()
                    )
                except Exception:
                    user_obj = None

                LoginLog.objects.create(
                    user=user_obj,
                    is_login=False,
                    login_result=failure_type,
                    ip_address=ip,
                    user_agent=user_agent,
                )

            for field in ("username", "password"):
                if field in errors:
                    return Response(
                        {"error": errors[field][0]}, status=status.HTTP_400_BAD_REQUEST
                    )
            if "non_field_errors" in errors:
                return Response(
                    {"error": errors["non_field_errors"][0]},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            return Response(
                {"error": "입력값을 확인해주세요."}, status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.validated_data["user"]

        LoginLog.objects.create(
            user=user,
            is_login=True,
            login_result=LoginLog.LoginResult.SUCCESS,
            ip_address=ip,
            user_agent=user_agent,
        )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "username": user.username,
                "role": user.user_type,
            }
        )


class MeView(APIView):
    """
    GET /api/auth/me/

    현재 로그인한 사용자의 기본 정보 및 메뉴 트리 반환.
    관리자(facility_admin, super_admin)에게는 admin_url도 포함.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="내 정보 + 메뉴 트리 조회",
        description=(
            "JWT 인증된 사용자의 ID/username/role/menu_tree를 반환한다. "
            "관리자 권한(facility_admin/super_admin)이면 `admin_url`도 포함되어 어드민 패널 진입점을 노출한다."
        ),
        responses={
            200: inline_serializer(
                name="MeResponse",
                fields={
                    "id": serializers.IntegerField(),
                    "username": serializers.CharField(),
                    "role": serializers.CharField(),
                    "menu_tree": serializers.ListField(child=serializers.DictField()),
                    "admin_url": serializers.CharField(
                        required=False, help_text="관리자 권한일 때만 포함"
                    ),
                },
            ),
            401: OpenApiResponse(description="JWT 누락/만료"),
        },
        examples=[
            OpenApiExample(
                "관리자 응답",
                value={
                    "id": 1,
                    "username": "admin",
                    "role": "super_admin",
                    "menu_tree": [
                        {
                            "id": 1,
                            "label": "나의 정보 확인",
                            "icon": "shield",
                            "children": [],
                        },
                        {
                            "id": 2,
                            "label": "모니터링",
                            "icon": "monitor",
                            "children": [],
                        },
                    ],
                    "admin_url": "/admin-panel/accounts-management/",
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "일반 작업자 응답",
                value={
                    "id": 5,
                    "username": "worker01",
                    "role": "worker",
                    "menu_tree": [
                        {
                            "id": 1,
                            "label": "나의 정보 확인",
                            "icon": "shield",
                            "children": [],
                        },
                    ],
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request):
        user = request.user
        try:
            menu_tree = get_menu_tree(user.user_type)
        except Exception:
            menu_tree = []

        data = {
            "id": user.id,
            "username": user.username,
            "role": user.user_type,
            "menu_tree": menu_tree,
        }
        if user.user_type in ("facility_admin", "super_admin"):
            data["admin_url"] = getattr(
                settings, "ADMIN_BACKOFFICE_URL", "/admin-panel/accounts-management/"
            )
        return Response(data)


class MyProfileView(APIView):
    """
    GET /api/auth/profile/

    현재 로그인한 사용자의 상세 프로필 반환.
    부서·직급·공장 FK를 select_related로 한 번에 조회.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="내 상세 프로필 조회",
        description="부서·직급·공장 정보까지 포함한 사용자 프로필.",
        responses={
            200: MyProfileSerializer,
            401: OpenApiResponse(description="JWT 누락/만료"),
        },
    )
    def get(self, request):
        user = (
            get_user_model()
            .objects.prefetch_related("dept_memberships__department")
            .select_related("position", "facility")
            .get(pk=request.user.pk)
        )
        return Response(MyProfileSerializer(user).data)


class PasswordChangeView(APIView):
    """
    POST /api/auth/password/change/

    현재 비밀번호 확인 후 새 비밀번호로 변경.
    유효성 검사(길이·복잡도·현재비밀번호 동일 여부)는 PasswordChangeSerializer에서 처리.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="비밀번호 변경",
        description="현재 비밀번호 확인 후 새 비밀번호로 변경. 길이·복잡도·중복 검사 포함.",
        request=PasswordChangeSerializer,
        responses={
            200: inline_serializer(
                name="OkResponse", fields={"ok": serializers.BooleanField()}
            ),
            400: OpenApiResponse(
                description="검증 실패 (현재 비밀번호 불일치, 새 비밀번호 정책 위반 등)"
            ),
            401: OpenApiResponse(description="JWT 누락/만료"),
        },
    )
    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        return Response({"ok": True})


class LogoutView(APIView):
    """
    POST /api/auth/logout/

    로그아웃 이력을 LoginLog에 기록하고 세션을 초기화.
    JWT는 stateless이므로 클라이언트에서 토큰을 직접 폐기해야 한다.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="로그아웃",
        description=(
            "LoginLog에 LOGOUT 이력 기록 + Django 세션 초기화. "
            "JWT는 stateless라 서버 측에서 토큰을 폐기하지 않으므로 클라이언트가 직접 토큰을 삭제해야 한다."
        ),
        request=None,
        responses={
            200: inline_serializer(
                name="LogoutOk", fields={"ok": serializers.BooleanField()}
            ),
            401: OpenApiResponse(description="JWT 누락/만료"),
        },
    )
    def post(self, request):
        LoginLog.objects.create(
            user=request.user,
            is_login=False,
            login_result=LoginLog.LoginResult.LOGOUT,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        )
        request.session.flush()
        return Response({"ok": True})
