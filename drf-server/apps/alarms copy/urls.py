from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AlarmRecordViewSet, MyStatusView, WorkerSummaryView

router = DefaultRouter()
router.register(r"", AlarmRecordViewSet, basename="alarm")

urlpatterns = [
    # ── API (/alarms/api/...) ────────────────────────────
    path("api/", include(router.urls)),
    path("api/my-status/", MyStatusView.as_view(), name="alarm-my-status"),
    path(
        "api/worker-summary/", WorkerSummaryView.as_view(), name="alarm-worker-summary"
    ),
]
