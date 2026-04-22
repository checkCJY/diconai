# monitoring/urls_cjy.py
from django.urls import path

from apps.monitoring.views.views_cjy import (
    PowerDataBulkIngestView_cjy,
    PowerEventIngestView_cjy,
)

urlpatterns = [
    path("api/power/event/", PowerEventIngestView_cjy.as_view()),
    path("api/power/data/", PowerDataBulkIngestView_cjy.as_view()),
    # 더미 스크립트 대응용 경로
    path("api/power/onoff/", PowerDataBulkIngestView_cjy.as_view()),
    path("api/power/current/", PowerDataBulkIngestView_cjy.as_view()),
    path("api/power/voltage/", PowerDataBulkIngestView_cjy.as_view()),
    path("api/power/watt/", PowerDataBulkIngestView_cjy.as_view()),
]
