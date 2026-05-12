"""
apps/safety/urls.py — 운영자 공용 라우터 (인증된 사용자 누구나 접근 가능).

URL 프리픽스: `/api/safety/` (config/urls.py에서 include).
어드민 전용 CRUD 라우터(`apps/safety/admin_urls.py`, 프리픽스 `/api/admin/safety/`)와
의도적으로 분리해 권한 경계를 URL 레벨에서도 명확히 한다.

현재 1개 endpoint(`checklist/active/`)만 노출 — 현장 작업자 페이지가 활성 Revision
스냅샷을 받아 동적 렌더링하는 용도. 향후 운영자용 read-only API가 늘어나면 본 파일에
계속 추가.
"""

from django.urls import path

from apps.safety.views.admin_views import ActiveChecklistView

urlpatterns = [
    path(
        "checklist/active/",
        ActiveChecklistView.as_view(),
        name="safety-checklist-active",
    ),
]
