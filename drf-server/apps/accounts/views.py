from datetime import datetime

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import LoginSerializer


# ──────────────────────────────────────────────────────────
# 권한별 메뉴 트리 정의
# ──────────────────────────────────────────────────────────
_MENU_WORKER = [
    {
        "id": "safety",
        "label": "나의 안전확인",
        "icon": "shield",
        "children": [
            {"id": "SNB-02", "label": "작업 전 안전 확인", "path": "/safety/checklist"},
            {"id": "SNB-04", "label": "안전 확인 이력", "path": "/safety/history"},
        ],
    },
    {
        "id": "monitoring",
        "label": "모니터링",
        "icon": "monitor",
        "children": [
            {
                "id": "SNB-06",
                "label": "실시간 모니터링",
                "path": "/monitoring/realtime",
            },
            {"id": "SNB-07", "label": "유해가스 현황", "path": "/monitoring/gas"},
            {"id": "SNB-08", "label": "스마트전력 현황", "path": "/monitoring/power"},
            {"id": "SNB-09", "label": "작업자 현황", "path": "/monitoring/workers"},
            {"id": "SNB-10", "label": "이벤트 현황", "path": "/monitoring/events"},
        ],
    },
]

_MENU_ADMIN_EXTRA = {
    "id": "admin_only",
    "label": "관리자 전용",
    "icon": "settings",
    "children": [
        {"id": "SNB-05", "label": "전체 이력 현황", "path": "/admin-panel/history"},
    ],
}


def get_menu_tree(role: str) -> list:
    import copy

    menus = copy.deepcopy(_MENU_WORKER)
    if role in ("admin", "superadmin"):
        import copy as _copy

        menus.append(_copy.deepcopy(_MENU_ADMIN_EXTRA))
    return menus


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


# ──────────────────────────────────────────────────────────
# GET /api/menu/
# ──────────────────────────────────────────────────────────
class MenuView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            menu = get_menu_tree(request.user.user_type)
        except Exception:
            return Response(
                {"error": "메뉴를 불러올 수 없습니다."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response({"menu": menu})


# ──────────────────────────────────────────────────────────
# GET /api/dashboard/refresh/
# ──────────────────────────────────────────────────────────
class DashboardRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = {"last_updated": datetime.now().isoformat()}
        if request.user.user_type in ("admin", "superadmin"):
            data["admin_url"] = getattr(settings, "ADMIN_BACKOFFICE_URL", "/admin/")
        return Response(data)
