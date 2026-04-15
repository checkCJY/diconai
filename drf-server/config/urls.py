from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from apps.accounts.views import login_view


# 작동확인용
def dashboard(request):
    return render(request, "dashboard_web.html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", login_view),
    path("dashboard/", dashboard),
]
