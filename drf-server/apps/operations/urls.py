from django.urls import path

from apps.operations.views.admin import (
    AppLogAdminListView,
    IntegrationLogAdminListView,
    DataRetentionPolicyListView,
    DataRetentionPolicyDetailView,
    DataRetentionPolicyPreviewView,
    DataRetentionPolicyRunView,
)
from apps.operations.views.internal.integration_log import (
    IntegrationLogInternalCreateView,
)

app_name = "operations"

urlpatterns = [
    # ── 내부 호출 (FastAPI → DRF) ───────────────────────────────────────────
    path(
        "internal/integration-logs/",
        IntegrationLogInternalCreateView.as_view(),
        name="internal-integration-log-create",
    ),

    # ── 관리자 조회 ─────────────────────────────────────────────────────────
    # GET /api/admin/system-logs/     — AppLog 조회
    # GET /api/admin/integration-logs/ — IntegrationLog 조회
    #
    # config/urls.py에서 "api/" 아래에 이 파일을 include하므로
    # 여기서 "admin/"을 붙이면 최종 URL은 /api/admin/...이 된다.
    path("admin/system-logs/", AppLogAdminListView.as_view(), name="admin-system-logs"),
    path("admin/integration-logs/", IntegrationLogAdminListView.as_view(), name="admin-integration-logs"),

    # ── 데이터 보관 정책 ────────────────────────────────────────────────────
    path(
        "admin/retention-policies/",
        DataRetentionPolicyListView.as_view(),
        name="admin-retention-policy-list",
    ),
    path(
        "admin/retention-policies/<int:pk>/",
        DataRetentionPolicyDetailView.as_view(),
        name="admin-retention-policy-detail",
    ),
    path(
        "admin/retention-policies/<int:pk>/preview/",
        DataRetentionPolicyPreviewView.as_view(),
        name="admin-retention-policy-preview",
    ),
    # POST /api/admin/retention-policies/run/  — 배치 즉시 실행 (dry_run 지원)
    path(
        "admin/retention-policies/run/",
        DataRetentionPolicyRunView.as_view(),
        name="admin-retention-policy-run",
    ),
]
