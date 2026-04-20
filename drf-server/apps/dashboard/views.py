from datetime import datetime

from django.conf import settings
from django.shortcuts import render
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .menu import get_menu_tree


# ──────────────────────────────────────────────────────────
# HTML 페이지 뷰
# ──────────────────────────────────────────────────────────
def main_dashboard(request):
    return render(request, "main_dashboard.html")


def safety_checklist_page(request):
    return render(request, "snb_details/safety_checklist.html")


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
                status=500,
            )
        return Response({"menu": menu})


# ──────────────────────────────────────────────────────────
# GET /api/dashboard/refresh/
# ──────────────────────────────────────────────────────────
class DashboardRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = {"last_updated": datetime.now().isoformat()}
        if request.user.user_type in ("facility_admin", "super_admin"):
            data["admin_url"] = getattr(settings, "ADMIN_BACKOFFICE_URL", "/admin/")
        return Response(data)
