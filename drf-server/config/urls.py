from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path

from apps.accounts.views import DashboardRefreshView, MenuView


def login_page(request):
    return render(request, "login.html")


def main_dashboard(request):
    return render(request, "main_dashboard.html")


def safety_checklist_page(request):
    return render(request, "safety_checklist.html")


def alarm_panel(request):
    return render(request, "alarm_panel.html")


# 기존 개별 대시보드 — 하위 호환용 (리팩토링 후에도 직접 접근 가능)
def dashboard_jh(request):
    return render(request, "dashboard_jh.html")


def dashboard_sh(request):
    return render(request, "dashboard_sh.html")


def dashboard_cjy(request):
    return render(request, "dashboard_CJY.html")


urlpatterns = [
    # Django 관리자
    path("admin/", admin.site.urls),
    # ── HTML 페이지 ──────────────────────────────────────
    path("login/", login_page, name="login"),
    # 통합 메인 대시보드 (루트 + /dashboard/)
    path("", main_dashboard, name="main-dashboard"),
    path("dashboard/", main_dashboard, name="main-dashboard-alt"),
    path("safety/checklist/", safety_checklist_page, name="safety-checklist"),
    path("alarm/", alarm_panel, name="alarm-panel"),
    # 기존 개별 대시보드 (하위 호환)
    path("dashboard_jh/", dashboard_jh, name="dashboard-jh"),
    path("dashboard_sh/", dashboard_sh, name="dashboard-sh"),
    path("dashboard-cjy/", dashboard_cjy, name="dashboard-cjy"),
    # ── API ──────────────────────────────────────────────
    path("api/auth/", include("apps.accounts.urls")),
    path("api/menu/", MenuView.as_view(), name="api-menu"),
    path(
        "api/dashboard/refresh/",
        DashboardRefreshView.as_view(),
        name="api-dashboard-refresh",
    ),
    path("api/alarms/", include("apps.alarms.urls")),
    path("api/", include("apps.alarms.urls")),
]
