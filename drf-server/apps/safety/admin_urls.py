"""
apps/safety/admin_urls.py — 어드민 전용 라우터 (슈퍼관리자·시설관리자 한정).

URL 프리픽스: `/api/admin/safety/` (config/urls.py에서 include).
운영자 공용 라우터(`apps/safety/urls.py`, 프리픽스 `/api/safety/`)와 의도적으로 분리.

[라우트 그룹]
- checklist/state/        — 페이지 헤더 메타 (최근 반영일, 편집 중 여부)
- sections/...            — 섹션 CRUD + reorder + 섹션별 문항 생성
- items/...               — 문항 CRUD + duplicate + reorder
- checklist/publish/      — 반영 저장 (SafetyChecklistRevision 스냅샷 발행)
- checklist/revisions/... — 반영 이력 리스트 + 단건 스냅샷 조회

[순서 규칙]
구체 path를 우선 등록 (예: `sections/reorder/` → `sections/<int:pk>/`).
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
