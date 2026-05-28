# monitoring/urls.py — 가스 + 전력 통합 라우터
# 모든 경로는 config/urls.py의 "api/monitoring/" 프리픽스 기준
# → 실제 URL: /api/monitoring/gas/, /api/monitoring/power/event/ 등
from django.urls import path

from apps.monitoring.views import (
    GasDataCreateView,
    GasThresholdView,
    PowerChannelMetaView,
    PowerDataBulkIngestView,
    PowerEventIngestView,
    PowerThresholdMetaView,
    PowerThresholdView,
)

urlpatterns = [
    path("gas/", GasDataCreateView.as_view(), name="gas-data-create"),
    path("gas/thresholds/", GasThresholdView.as_view(), name="gas-thresholds"),
    path("power/thresholds/", PowerThresholdView.as_view(), name="power-thresholds"),
    # T4 D1b — fastapi 5분 sync 용 정격 % 임계치 (power_facility_default 그룹).
    path(
        "power/threshold-meta/",
        PowerThresholdMetaView.as_view(),
        name="power-threshold-meta",
    ),
    path(
        "power/channel-meta/",
        PowerChannelMetaView.as_view(),
        name="power-channel-meta",
    ),
    path("power/event/", PowerEventIngestView.as_view(), name="power-event-ingest"),
    path("power/data/", PowerDataBulkIngestView.as_view(), name="power-data-ingest"),
]
