from django.urls import path

from . import views

urlpatterns = [
    # ── HTML 페이지 ──────────────────────────────────────
    path("", views.main_dashboard, name="main-dashboard"),
    path("safety/checklist/", views.safety_checklist_page, name="safety-checklist"),
    # ── API ──────────────────────────────────────────────
    path("api/menu/", views.MenuView.as_view(), name="api-menu"),
    path(
        "api/refresh/",
        views.DashboardRefreshView.as_view(),
        name="api-dashboard-refresh",
    ),
]
