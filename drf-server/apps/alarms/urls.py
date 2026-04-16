from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AlarmRecordViewSet

router = DefaultRouter()
router.register(r'alarms', AlarmRecordViewSet, basename='alarm')

urlpatterns = [
    path('', include(router.urls)),
]