from django.urls import path

from . import views
from django.views.generic import TemplateView

urlpatterns = [
    # ── HTML 페이지 ──────────────────────────────────────
    path("", views.main_dashboard, name="main-dashboard"),
    path("safety/checklist/", views.safety_checklist_page, name="safety-checklist"),
    path("admin/", TemplateView.as_view(template_name="admin/main.html")),
    # ── API ──────────────────────────────────────────────
    path("api/menu/", views.MenuView.as_view(), name="api-menu"),
    path(
        "api/refresh/",
        views.DashboardRefreshView.as_view(),
        name="api-dashboard-refresh",
    ),
]
