from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path

from apps.accounts.views import DashboardRefreshView, MenuView


def login_page(request):
    return render(request, "auth/login.html")


def main_dashboard(request):
    return render(request, "main_dashboard.html")


def safety_checklist_page(request):
    return render(request, "snb_details/safety_checklist.html")


urlpatterns = [
    # ── 관리자 ───────────────────────────────────────────
    path("admin/", admin.site.urls),
    # ── HTML 페이지 ──────────────────────────────────────
    path("", main_dashboard, name="main-dashboard"),
    path("dashboard/", main_dashboard, name="main-dashboard-alt"),
    path("login/", login_page, name="login"),
    path(
        "safety/checklist/",
        safety_checklist_page,
        name="safety-checklist",
    ),
    # ── API ──────────────────────────────────────────────
    path("api/auth/", include("apps.accounts.urls")),
    path("api/alarms/", include("apps.alarms.urls")),
    path("api/menu/", MenuView.as_view(), name="api-menu"),
    path(
        "api/dashboard/refresh/",
        DashboardRefreshView.as_view(),
        name="api-dashboard-refresh",
    ),
]
