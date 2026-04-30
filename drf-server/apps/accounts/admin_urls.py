"""
apps/accounts/admin_urls.py

어드민 패널 — 사용자/조직 관리 API URL 설정.
config/urls.py에서 "api/admin/" 프리픽스로 포함된다.
"""

from django.urls import path

from apps.accounts.views.admin_views import (
    AccountsAdminDetailView,
    AccountsAdminListView,
    AccountsAdminLockView,
)
from apps.accounts.views.org_views import (
    OrgTreeView,
    DeptListCreateView,
    DeptDetailView,
    DeptMemberListView,
    DeptMemberAddView,
    DeptMemberMoveView,
    DeptMemberRemoveView,
    DeptLeaderAssignView,
)

urlpatterns = [
    # ── 사용자 관리 ────────────────────────────────────────────
    path("accounts/", AccountsAdminListView.as_view(), name="admin-accounts-list"),
    path(
        "accounts/<int:pk>/",
        AccountsAdminDetailView.as_view(),
        name="admin-accounts-detail",
    ),
    path(
        "accounts/<int:pk>/<str:action>/",
        AccountsAdminLockView.as_view(),
        name="admin-accounts-lock",
    ),
    # ── 조직 관리 ──────────────────────────────────────────────
    path("organizations/tree/", OrgTreeView.as_view(), name="admin-org-tree"),
    path("departments/", DeptListCreateView.as_view(), name="admin-dept-list-create"),
    path("departments/<int:pk>/", DeptDetailView.as_view(), name="admin-dept-detail"),
    # ── 구성원 관리 (조직 없음은 pk="none") ────────────────────
    path(
        "departments/<pk>/members/",
        DeptMemberListView.as_view(),
        name="admin-dept-members",
    ),
    path(
        "departments/<int:pk>/members/add/",
        DeptMemberAddView.as_view(),
        name="admin-dept-member-add",
    ),
    path(
        "departments/<pk>/members/move/",
        DeptMemberMoveView.as_view(),
        name="admin-dept-member-move",
    ),
    path(
        "departments/<int:pk>/members/remove/",
        DeptMemberRemoveView.as_view(),
        name="admin-dept-member-remove",
    ),
    path(
        "departments/<int:pk>/members/assign-leader/",
        DeptLeaderAssignView.as_view(),
        name="admin-dept-leader",
    ),
]
