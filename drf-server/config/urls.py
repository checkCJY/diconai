from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from apps.accounts.urls import api_urlpatterns as auth_api_urlpatterns
from apps.accounts.urls import page_urlpatterns as auth_page_urlpatterns


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("accounts/", include(auth_page_urlpatterns)),
    path("api/auth/", include(auth_api_urlpatterns)),
    path("dashboard/", include("apps.dashboard.urls")),
    path("alerts/", include("apps.alerts.urls")),
    path("api/", include("apps.geofence.urls")),
    path("api/admin/", include("apps.accounts.admin_urls")),
    path("api/positioning/", include("apps.positioning.urls")),
    path("api/monitoring/", include("apps.monitoring.urls")),
    path("admin-panel/", include("config.admin_panel_urls")),
    path("api/", include("apps.facilities.urls")),
]
