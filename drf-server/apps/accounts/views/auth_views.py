"""
apps/accounts/views/auth_views.py

인증 관련 API 뷰 모음.
로그인, 로그아웃, 내 정보 조회, 비밀번호 변경 등
일반 사용자(비관리자 포함)가 사용하는 인증 흐름을 처리한다.

URL 프리픽스: /api/auth/
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
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
