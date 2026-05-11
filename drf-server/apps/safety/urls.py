"""
apps/safety/urls.py

현장 운영자/공용 — 안전 체크리스트 조회 API URL.
config/urls.py에서 "api/safety/" 프리픽스로 포함된다.
어드민 전용 CRUD는 apps/safety/admin_urls.py (프리픽스 /api/admin/safety/).
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
