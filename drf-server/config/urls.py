from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render


# 작동확인용
def dashboard(request):
    return render(request, "dashboard.html")


def dashboard_cjy(request):
    return render(request, "dashboard_CJY.html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", dashboard),
    path("dashboard-cjy/", dashboard_cjy),
    path("api/alarms/", include("apps.alarms.urls")),
]
