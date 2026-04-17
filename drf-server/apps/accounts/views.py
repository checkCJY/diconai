from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import LoginSerializer
from apps.dashboard.menu import get_menu_tree


# ──────────────────────────────────────────────────────────
# POST /api/auth/login/
# ──────────────────────────────────────────────────────────
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            errors = serializer.errors.get(
                "non_field_errors", ["입력값을 확인해주세요."]
            )
            return Response({"error": errors[0]}, status=status.HTTP_401_UNAUTHORIZED)

        user = serializer.validated_data["user"]
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

        return Response(
            {
                "username": user.username,
                "role": user.user_type,
                "menu_tree": menu_tree,
            }
        )
