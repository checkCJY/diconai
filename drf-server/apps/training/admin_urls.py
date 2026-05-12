"""
apps/training/admin_urls.py — VR 교육 어드민 라우트.

URL 프리픽스: `/api/admin/training/` (config/urls.py에서 include).
"""

from django.urls import path

from apps.training.views.admin_views import (
    VRTrainingDetailView,
    VRTrainingMetaUpdateView,
    VRTrainingReplaceView,
    VRTrainingRevisionListView,
)

urlpatterns = [
    path(
        "vr-training/",
        VRTrainingDetailView.as_view(),
        name="admin-vr-training-detail",
    ),
    path(
        "vr-training/replace/",
        VRTrainingReplaceView.as_view(),
        name="admin-vr-training-replace",
    ),
    path(
        "vr-training/<int:pk>/",
        VRTrainingMetaUpdateView.as_view(),
        name="admin-vr-training-meta",
    ),
    path(
        "vr-training/<int:pk>/revisions/",
        VRTrainingRevisionListView.as_view(),
        name="admin-vr-training-revisions",
    ),
]
