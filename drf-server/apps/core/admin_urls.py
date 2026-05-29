"""
core/admin_urls.py

사용자 활동 로그 / 지도 편집 로그 관리자 API URL 설정.

왜 urls.py가 아닌 admin_urls.py인가:
  apps/core/urls.py가 존재할 경우 내부 또는 공개 API URL과 혼재할 수 있다.
  admin_ prefix로 "이 파일은 관리자 API 전용"임을 파일 이름에서 바로 알 수 있다.
  apps.accounts, apps.monitoring과 동일한 네이밍 컨벤션을 따른다.

config/urls.py 등록:
  path("api/admin/", include("apps.core.admin_urls"))
  → 최종 URL: /api/admin/activity-logs/, /api/admin/map-edit-logs/
"""

from django.urls import path

from apps.core.views import MapEditLogAdminListView, SystemLogAdminListView
from apps.core.views.risk_standard_admin import (
    RiskStandardAdminDetailView,
    RiskStandardAdminListView,
)

urlpatterns = [
    # GET /api/admin/activity-logs/   — 사용자 활동 로그
    path("activity-logs/", SystemLogAdminListView.as_view(), name="admin-activity-logs"),

    # GET /api/admin/map-edit-logs/   — 지도 편집 로그 (MAP_ action만)
    path("map-edit-logs/", MapEditLogAdminListView.as_view(), name="admin-map-edit-logs"),

    # 위험 기준 관리
    path("risk-standards/", RiskStandardAdminListView.as_view(), name="admin-risk-standards-list"),
    path("risk-standards/<int:pk>/", RiskStandardAdminDetailView.as_view(), name="admin-risk-standards-detail"),
]
