"""
apps/accounts/admin_urls.py

어드민 패널 — 사용자 관리 API URL 설정.
config/urls.py에서 "api/admin/" 프리픽스로 포함된다.
"""

from django.urls import path

from apps.accounts.views.admin_views import (
    AccountsAdminDetailView,
    AccountsAdminListView,
    AccountsAdminLockView,
)

urlpatterns = [
    # 목록 조회 / 신규 등록
    path("accounts/", AccountsAdminListView.as_view(), name="admin-accounts-list"),
    # 상세 조회 / 수정 / 비활성화
    path(
        "accounts/<int:pk>/",
        AccountsAdminDetailView.as_view(),
        name="admin-accounts-detail",
    ),
    # 계정 잠금 / 잠금 해제  (?action=lock|unlock)
    path(
        "accounts/<int:pk>/<str:action>/",
        AccountsAdminLockView.as_view(),
        name="admin-accounts-lock",
    ),
]
