from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.alerts.views import AlarmRecordViewSet, MyStatusView, WorkerSummaryView

router = DefaultRouter()
router.register(r"", AlarmRecordViewSet, basename="alarm")

urlpatterns = [
    path("api/", include(router.urls)),
    path("api/my-status/", MyStatusView.as_view(), name="alarm-my-status"),
    path(
        "api/worker-summary/", WorkerSummaryView.as_view(), name="alarm-worker-summary"
    ),
]
