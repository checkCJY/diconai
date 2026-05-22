"""apps/alerts/admin_urls.py

어드민 패널 — 알림 정책 관리 API URL.
config/urls.py 에서 "api/admin/alerts/" 프리픽스로 포함된다.
"""

from django.urls import path

from apps.alerts.views.admin_views import (
    AlertPolicyAdminDetailView,
    AlertPolicyAdminListView,
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
]
