from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path

from apps.accounts.views import DashboardRefreshView, MenuView


# 지혜님 코드
def login_page(request):
    return render(request, "login.html")


def dashboard_page(request):
    return render(request, "dashboard_jh.html")


def safety_checklist_page(request):
    return render(request, "safety_checklist.html")


# 작동확인용
def dashboard(request):
    return render(request, "dashboard_sh.html")


def alarm_panel(request):
    return render(request, "alarm_panel.html")


def dashboard_cjy(request):
    return render(request, "dashboard_CJY.html")


urlpatterns = [
    # Django 관리자
    path("admin/", admin.site.urls),
    # HTML 페이지, 지혜님 코드
    path("login/", login_page, name="login"),
    path("dashboard_jh/", dashboard_page, name="dashboard"),
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
    path("", dashboard),
    # 최재용 코드
    path("dashboard-cjy/", dashboard_cjy),
    path("api/alarms/", include("apps.alarms.urls")),
    # 정휘훈 코드
    path("alarm/", alarm_panel),
    path("api/", include("apps.alarms.urls")),
]
