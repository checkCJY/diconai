"""reference/admin_urls.py

공통 코드 관리 어드민 API URL.
config/urls.py 에서 "api/admin/" 프리픽스로 포함된다.

[URL 표]
GET/POST   api/admin/code-groups/                   — 그룹 목록·생성
PATCH/DEL  api/admin/code-groups/<pk>/              — 그룹 수정·삭제
GET/POST   api/admin/code-groups/<pk>/codes/        — 코드 목록·생성
PATCH/DEL  api/admin/codes/<pk>/                    — 코드 수정·삭제
POST       api/admin/codes/bulk-deactivate/         — 코드 일괄 미사용
"""

from django.urls import path

from apps.reference.views.code_admin import (
    CodeGroupAdminDetailView,
    CodeGroupAdminListView,
    CommonCodeAdminDetailView,
    CommonCodeAdminListView,
    CommonCodeBulkDeactivateView,
)

urlpatterns = [
    # 코드 그룹
    path("code-groups/", CodeGroupAdminListView.as_view(), name="admin-code-groups"),
    path("code-groups/<int:pk>/", CodeGroupAdminDetailView.as_view(), name="admin-code-group-detail"),

    # 그룹별 코드 목록·생성
    path("code-groups/<int:group_id>/codes/", CommonCodeAdminListView.as_view(), name="admin-common-codes"),

    # 코드 수정·삭제
    path("codes/<int:pk>/", CommonCodeAdminDetailView.as_view(), name="admin-common-code-detail"),

    # 코드 일괄 미사용 전환
    path("codes/bulk-deactivate/", CommonCodeBulkDeactivateView.as_view(), name="admin-common-code-bulk-deactivate"),
]
