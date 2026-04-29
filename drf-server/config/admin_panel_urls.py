from django.urls import path
from django.views.generic import TemplateView
from apps.geofence.views.admin_views import GeoFenceAdminPageView
from apps.facilities.views.map_editor import MapEditorPageView
from apps.facilities.views.facility_admin import FacilityAdminPageView

urlpatterns = [
    path(
        "accounts-management/",
        TemplateView.as_view(
            template_name="admin_panel/accounts/accounts_main.html",
            extra_context={"active_nav": "account"},
        ),
        name="admin-accounts-page",
    ),
    path(
        "geofence/",
        GeoFenceAdminPageView.as_view(),
        name="admin-geofence-page",
    ),
    path(
        "map-editor/",
        MapEditorPageView.as_view(),
        name="admin-map-editor",
    ),
    path(
        "facility/",
        FacilityAdminPageView.as_view(),
        name="admin-facility",
    ),
]
