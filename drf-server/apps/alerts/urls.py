from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.alerts.views import (
    AlarmRecordViewSet,
    AnomalyAlarmRecordCreateView,
    EventViewSet,
    MyStatusView,
    WorkerSummaryView,
)

router = DefaultRouter()
router.register(r"alarms", AlarmRecordViewSet, basename="alarm")
router.register(r"events", EventViewSet, basename="event")

urlpatterns = [
    path("api/my-status/", MyStatusView.as_view(), name="alarm-my-status"),
    path(
        "api/worker-summary/", WorkerSummaryView.as_view(), name="alarm-worker-summary"
    ),
    path(
        "api/anomaly-alarm-records/",
        AnomalyAlarmRecordCreateView.as_view(),
        name="alarm-anomaly-alarm-records",
    ),
    path("api/", include(router.urls)),
]
