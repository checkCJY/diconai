"""
apps/safety/admin_urls.py

어드민 패널 — 작업 전 안전 점검 체크리스트 관리 API URL 설정.
config/urls.py에서 "api/admin/safety/" 프리픽스로 포함된다.
"""

from django.urls import path

from apps.safety.views.admin_views import (
    ChecklistItemCreateView,
    ChecklistItemDetailView,
    ChecklistItemDuplicateView,
    ChecklistItemReorderView,
    ChecklistPublishView,
    ChecklistRevisionDetailView,
    ChecklistRevisionListView,
    ChecklistSectionDetailView,
    ChecklistSectionListView,
    ChecklistSectionReorderView,
    ChecklistStateView,
)

urlpatterns = [
    # 헤더 메타 (최근 반영일, 편집 중 여부)
    path(
        "checklist/state/",
        ChecklistStateView.as_view(),
        name="admin-checklist-state",
    ),
    # 섹션
    path(
        "sections/",
        ChecklistSectionListView.as_view(),
        name="admin-checklist-sections",
    ),
    path(
        "sections/reorder/",
        ChecklistSectionReorderView.as_view(),
        name="admin-checklist-sections-reorder",
    ),
    path(
        "sections/<int:pk>/",
        ChecklistSectionDetailView.as_view(),
        name="admin-checklist-section-detail",
    ),
    path(
        "sections/<int:section_id>/items/",
        ChecklistItemCreateView.as_view(),
        name="admin-checklist-section-items",
    ),
    # 문항
    path(
        "items/reorder/",
        ChecklistItemReorderView.as_view(),
        name="admin-checklist-items-reorder",
    ),
    path(
        "items/<int:pk>/",
        ChecklistItemDetailView.as_view(),
        name="admin-checklist-item-detail",
    ),
    path(
        "items/<int:pk>/duplicate/",
        ChecklistItemDuplicateView.as_view(),
        name="admin-checklist-item-duplicate",
    ),
    # 반영 저장 + 이력
    path(
        "checklist/publish/",
        ChecklistPublishView.as_view(),
        name="admin-checklist-publish",
    ),
    path(
        "checklist/revisions/",
        ChecklistRevisionListView.as_view(),
        name="admin-checklist-revisions",
    ),
    path(
        "checklist/revisions/<int:pk>/",
        ChecklistRevisionDetailView.as_view(),
        name="admin-checklist-revision-detail",
    ),
]
