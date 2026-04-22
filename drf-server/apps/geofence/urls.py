# apps/geofence/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.geofence.views import GeoFenceViewSet

router = DefaultRouter()
router.register(r"geofences", GeoFenceViewSet, basename="geofence")

urlpatterns = [
    path("", include(router.urls)),
]
