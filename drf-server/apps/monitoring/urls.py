# monitoring/urls.py — 가스 + 전력 통합 라우터
from django.urls import path

from apps.monitoring.views import (
    GasDataCreateView,
    PowerDataBulkIngestView,
    PowerEventIngestView,
)

urlpatterns = [
    # 가스 — POST /api/monitoring/gas/
    path("gas/", GasDataCreateView.as_view(), name="gas-data-create"),
    # 전력 — POST /monitoring/api/power/*/  (FastAPI power_system/router_cjy.py 호출 경로)
    path("api/power/event/", PowerEventIngestView.as_view(), name="power-event-ingest"),
    path(
        "api/power/data/", PowerDataBulkIngestView.as_view(), name="power-data-ingest"
    ),
    path(
        "api/power/onoff/", PowerDataBulkIngestView.as_view(), name="power-onoff-ingest"
    ),
    path(
        "api/power/current/",
        PowerDataBulkIngestView.as_view(),
        name="power-current-ingest",
    ),
    path(
        "api/power/voltage/",
        PowerDataBulkIngestView.as_view(),
        name="power-voltage-ingest",
    ),
    path(
        "api/power/watt/", PowerDataBulkIngestView.as_view(), name="power-watt-ingest"
    ),
]
