from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.accounts.urls import api_urlpatterns as auth_api_urlpatterns
from apps.accounts.urls import page_urlpatterns as auth_page_urlpatterns
from apps.core.prometheus import metrics_view


def health_check(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health"),
    path("metrics", metrics_view, name="metrics"),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("accounts/", include(auth_page_urlpatterns)),
    path("api/auth/", include(auth_api_urlpatterns)),
    path("dashboard/", include("apps.dashboard.urls")),
    path("alerts/", include("apps.alerts.urls")),
    path("api/", include("apps.geofence.urls")),
    path("api/admin/", include("apps.accounts.admin_urls")),
    path("api/admin/", include("apps.monitoring.admin_urls")),
    path("api/admin/safety/", include("apps.safety.admin_urls")),
    path("api/admin/training/", include("apps.training.admin_urls")),
    path("api/safety/", include("apps.safety.urls")),
    path("api/positioning/", include("apps.positioning.urls")),
    path("api/monitoring/", include("apps.monitoring.urls")),
    path("admin-panel/", include("config.admin_panel_urls")),
    path("api/", include("apps.facilities.urls")),
    path("api/", include("apps.operations.urls")),
    # OpenAPI / Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-swagger-ui",
    ),
    path(
        "api/schema/redoc/",
        SpectacularRedocView.as_view(url_name="api-schema"),
        name="api-redoc",
    ),
]

if settings.DEBUG:
    # 개발 환경 한정 MEDIA 서빙. 운영은 nginx/CDN에서 처리.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
