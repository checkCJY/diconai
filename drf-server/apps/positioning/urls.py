# apps/positioning/urls.py
from django.urls import path
from apps.positioning.views import WorkerPositionReceiveView

urlpatterns = [
    path("receive/", WorkerPositionReceiveView.as_view(), name="position-receive"),
]
