from django.urls import path

from apps.monitoring.views import GasDataCreateView

urlpatterns = [
    path("gas/", GasDataCreateView.as_view(), name="gas-data-create"),
]
