from datetime import datetime, date

from django.conf import settings
from django.shortcuts import render
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .menu import get_menu_tree


# ──────────────────────────────────────────────────────────
# HTML 페이지 뷰
# ──────────────────────────────────────────────────────────
def main_dashboard(request):
    return render(request, "main_dashboard.html")


def main_dashboard_jhh(request):
    return render(request, "main_dashboard_jhh.html")


def safety_checklist_page(request):
    return render(request, "snb_details/safety_checklist.html")


def safety_history_page(request):
    return render(request, "snb_details/safety_history.html")


def safety_vr_page(request):
    return render(request, "snb_details/safety_vr.html")


def monitoring_realtime_page(request):
    return render(request, "snb_details/monitoring_realtime.html")


def monitoring_gas_page(request):
    return render(request, "snb_details/monitoring_gas.html")


def monitoring_power_page(request):
    return render(request, "snb_details/monitoring_power.html")


def monitoring_workers_page(request):
    return render(request, "snb_details/monitoring_workers.html")


def monitoring_events_page(request):
    return render(request, "snb_details/monitoring_events.html")


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
# ──────────────────────────────────────────────────────────
# GET/POST /api/vr-progress/ — VR 시청 위치 임시 저장 (세션)
# ──────────────────────────────────────────────────────────
class VRProgressView(APIView):
    permission_classes = [AllowAny]

    SESSION_KEY = "vr_safety_progress"

    def get(self, request):
        position = request.session.get(self.SESSION_KEY, 0)
        return Response({"position": position})

    def post(self, request):
        try:
            position = float(request.data.get("position", 0))
        except (TypeError, ValueError):
            position = 0
        request.session[self.SESSION_KEY] = position
        return Response({"saved": position})


# ──────────────────────────────────────────────────────────
# GET/POST /api/safety-status/ — 나의 안전확인 완료 상태 (세션 기반)
# ──────────────────────────────────────────────────────────
class MySafetyStatusView(APIView):
    permission_classes = [AllowAny]

    CHECKLIST_KEY = "safety_checklist_done_date"
    VR_KEY = "safety_vr_done_date"

    def _is_done_today(self, request, key):
        stored = request.session.get(key)
        return stored == str(date.today())

    def get(self, request):
        return Response(
            {
                "checklist_done": self._is_done_today(request, self.CHECKLIST_KEY),
                "vr_done": self._is_done_today(request, self.VR_KEY),
            }
        )

    def post(self, request):
        key_name = request.data.get("key")
        if key_name == "checklist":
            request.session[self.CHECKLIST_KEY] = str(date.today())
        elif key_name == "vr":
            request.session[self.VR_KEY] = str(date.today())
        else:
            return Response(
                {"error": "key는 'checklist' 또는 'vr'이어야 합니다."}, status=400
            )
        return Response({"ok": True})


class DashboardRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = {"last_updated": datetime.now().isoformat()}
        if request.user.user_type in ("facility_admin", "super_admin"):
            data["admin_url"] = getattr(settings, "ADMIN_BACKOFFICE_URL", "/admin/")
        return Response(data)
