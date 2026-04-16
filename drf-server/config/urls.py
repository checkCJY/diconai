from django.contrib import admin
from django.urls import path ,include
from django.shortcuts import render


# 작동확인용
def dashboard(request):
    return render(request, "dashboard.html")

def alarm_panel(request):
    return render(request, "alarm_panel.html")
    


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", dashboard),
    path("alarm/", alarm_panel),
    path('api/', include('apps.alarms.urls')),
]
