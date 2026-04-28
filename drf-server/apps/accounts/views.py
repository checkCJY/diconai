from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models.login_log import LoginLog
from .serializers import LoginSerializer, MyProfileSerializer, PasswordChangeSerializer
from apps.dashboard.menu import get_menu_tree


def _get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ──────────────────────────────────────────────────────────
# POST /api/auth/login/
# ──────────────────────────────────────────────────────────
class LoginView(APIView):
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


# ──────────────────────────────────────────────────────────
# GET /api/auth/me/
# ──────────────────────────────────────────────────────────
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            menu_tree = get_menu_tree(user.user_type)
        except Exception:
            menu_tree = []

        data = {
            "username": user.username,
            "role": user.user_type,
            "menu_tree": menu_tree,
        }
        if user.user_type in ("facility_admin", "super_admin"):
            data["admin_url"] = getattr(
                settings, "ADMIN_BACKOFFICE_URL", "/admin-panel/accounts-management/"
            )
        return Response(data)


# ──────────────────────────────────────────────────────────
# GET /api/auth/profile/
# ──────────────────────────────────────────────────────────
class MyProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = (
            get_user_model()
            .objects.select_related("department", "position", "facility")
            .get(pk=request.user.pk)
        )
        return Response(MyProfileSerializer(user).data)


# ──────────────────────────────────────────────────────────
# POST /api/auth/password/change/
# ──────────────────────────────────────────────────────────
class PasswordChangeView(APIView):
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


# ──────────────────────────────────────────────────────────
# POST /api/auth/logout/
# ──────────────────────────────────────────────────────────
class LogoutView(APIView):
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
