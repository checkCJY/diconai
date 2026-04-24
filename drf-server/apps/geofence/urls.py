from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.geofence.views import GeoFenceViewSet
from apps.geofence.views.admin_views import (
    GeoFenceAdminListView,
    GeoFenceAdminDetailView,
)

router = DefaultRouter()
router.register(r"geofences", GeoFenceViewSet, basename="geofence")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "admin/geofences/", GeoFenceAdminListView.as_view(), name="admin-geofence-list"
    ),
    path(
        "admin/geofences/<int:pk>/",
        GeoFenceAdminDetailView.as_view(),
        name="admin-geofence-detail",
    ),
]
