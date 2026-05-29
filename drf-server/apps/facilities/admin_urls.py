"""facilities/admin_urls.py

임계치 기준 관리 어드민 API URL.
config/urls.py 에서 "api/admin/" 프리픽스로 포함된다.
"""

from django.urls import path

from apps.facilities.views.threshold_admin import (
    ThresholdAdminDetailView,
    ThresholdAdminListView,
    ThresholdBulkDeactivateView,
    ThresholdGroupAdminDetailView,
    ThresholdGroupAdminListView,
)

urlpatterns = [
    # 분류 그룹
    path("threshold-groups/", ThresholdGroupAdminListView.as_view(), name="admin-threshold-groups"),
    path("threshold-groups/<int:pk>/", ThresholdGroupAdminDetailView.as_view(), name="admin-threshold-group-detail"),

    # 그룹별 임계치 목록/생성
    path("threshold-groups/<int:group_id>/thresholds/", ThresholdAdminListView.as_view(), name="admin-thresholds"),

    # 임계치 수정/삭제
    path("thresholds/<int:pk>/", ThresholdAdminDetailView.as_view(), name="admin-threshold-detail"),

    # 임계치 일괄 미사용 전환
    path("thresholds/bulk-deactivate/", ThresholdBulkDeactivateView.as_view(), name="admin-threshold-bulk-deactivate"),
]
