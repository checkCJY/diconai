from django.urls import path
from .views import MyStatusView, WorkerSummaryView

urlpatterns = [
    path("my-status/", MyStatusView.as_view(), name="alarm-my-status"),
    path("worker-summary/", WorkerSummaryView.as_view(), name="alarm-worker-summary"),
]
