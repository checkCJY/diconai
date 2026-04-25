# apps/geofence/admin_urls.py
from django.urls import path
from apps.geofence.views.admin_views import GeoFenceAdminPageView

urlpatterns = [
    path("geofence/", GeoFenceAdminPageView.as_view(), name="admin-geofence-page"),
]
