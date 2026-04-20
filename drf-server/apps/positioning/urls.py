from django.urls import path
from apps.positioning.views import PositionReceiveView

urlpatterns = [
    path("api/receive/", PositionReceiveView.as_view(), name="position-receive"),
]
