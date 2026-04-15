from django.contrib import admin
from django.urls import path
from django.shortcuts import render


# 작동확인용
def dashboard(request):
    return render(request, "dashboard.html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("dashboard/", dashboard),
]
