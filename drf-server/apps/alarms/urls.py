from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AlarmRecordViewSet, MyStatusView, WorkerSummaryView
# AlarmRecordViewSet -> 정휘훈 코드
# MyStatusView, WorkerSummaryView -> 최재용 코드

router = DefaultRouter()
router.register(r"alarms", AlarmRecordViewSet, basename="alarm")

urlpatterns = [
    # 정휘훈 코드
    path("", include(router.urls)),
    # 최재용 코드
    path("my-status/", MyStatusView.as_view(), name="alarm-my-status"),
    path("worker-summary/", WorkerSummaryView.as_view(), name="alarm-worker-summary"),
]
