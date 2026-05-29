"""apps/alerts/admin_urls.py

어드민 패널 — 알림 정책 관리 API URL.
config/urls.py 에서 "api/admin/alerts/" 프리픽스로 포함된다.
"""

from django.urls import path

from apps.alerts.views.admin_views import (
    AlertPolicyAdminDetailView,
    AlertPolicyAdminListView,
    EventHistoryAdminListView,
)

urlpatterns = [
    path(
        "policies/",
        AlertPolicyAdminListView.as_view(),
        name="admin-alert-policies-list",
    ),
    path(
        "policies/<int:pk>/",
        AlertPolicyAdminDetailView.as_view(),
        name="admin-alert-policies-detail",
    ),
    # GET /api/admin/alerts/events/ — 이벤트 이력 조회 (읽기 전용)
    path(
        "events/",
        EventHistoryAdminListView.as_view(),
        name="admin-event-history-list",
    ),
]
