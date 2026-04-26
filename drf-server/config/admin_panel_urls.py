from django.urls import path
from django.views.generic import TemplateView
from apps.geofence.views.admin_views import GeoFenceAdminPageView

urlpatterns = [
    path(
        "accounts-management/",
        TemplateView.as_view(
            template_name="admin/accounts/accounts_main.html",
            extra_context={"active_nav": "account"},
        ),
        name="admin-accounts-page",
    ),
    path(
        "geofence/",
        GeoFenceAdminPageView.as_view(),
        name="admin-geofence-page",
    ),
]
