from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.alerts.views import AlarmRecordViewSet, MyStatusView, WorkerSummaryView

router = DefaultRouter()
router.register(r"", AlarmRecordViewSet, basename="alarm")

urlpatterns = [
    # 구체적인 경로를 router include보다 먼저 선언 — 그렇지 않으면 router가 가로챔
    path("api/my-status/", MyStatusView.as_view(), name="alarm-my-status"),
    path(
        "api/worker-summary/", WorkerSummaryView.as_view(), name="alarm-worker-summary"
    ),
    path("api/", include(router.urls)),
]
