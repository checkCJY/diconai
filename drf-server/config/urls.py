from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render


# 작동확인용
def dashboard(request):
    return render(request, "dashboard_sh.html")


def alarm_panel(request):
    return render(request, "alarm_panel.html")


def dashboard_cjy(request):
    return render(request, "dashboard_CJY.html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", dashboard),
    # 최재용 코드
    path("dashboard-cjy/", dashboard_cjy),
    path("api/alarms/", include("apps.alarms.urls")),
    # 정휘훈 코드
    path("alarm/", alarm_panel),
    path("api/", include("apps.alarms.urls")),
]
