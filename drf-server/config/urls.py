from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path

from apps.accounts.views import DashboardRefreshView, MenuView


def login_page(request):
    return render(request, "login.html")


def dashboard_page(request):
    return render(request, "dashboard_jh.html")


def safety_checklist_page(request):
    return render(request, "safety_checklist.html")


urlpatterns = [
    # Django 관리자
    path("admin/", admin.site.urls),
    # HTML 페이지
    path("login/", login_page, name="login"),
    path("", dashboard_page, name="dashboard"),
    path("safety/checklist/", safety_checklist_page, name="safety-checklist"),
    # API — 인증
    path("api/auth/", include("apps.accounts.urls")),
    # API — 메뉴 트리
    path("api/menu/", MenuView.as_view(), name="api-menu"),
    # API — 대시보드 새로고침
    path(
        "api/dashboard/refresh/",
        DashboardRefreshView.as_view(),
        name="api-dashboard-refresh",
    ),
]
