from django.urls import path

from . import views

urlpatterns = [
    # ── HTML 페이지 ──────────────────────────────────────
    path("", views.main_dashboard, name="main-dashboard"),
    path("profile/", views.my_profile_page, name="my-profile"),
    path("safety/checklist/", views.safety_checklist_page, name="safety-checklist"),
    path("safety/history/", views.safety_history_page, name="safety-history"),
    path("safety/vr/", views.safety_vr_page, name="safety-vr"),
    path("api/vr-progress/", views.VRProgressView.as_view(), name="vr-progress"),
    path(
        "monitoring/realtime/",
        views.monitoring_realtime_page,
        name="monitoring-realtime",
    ),
    path("monitoring/gas/", views.monitoring_gas_page, name="monitoring-gas"),
    path("monitoring/power/", views.monitoring_power_page, name="monitoring-power"),
    path(
        "monitoring/workers/", views.monitoring_workers_page, name="monitoring-workers"
    ),
    path("monitoring/events/", views.monitoring_events_page, name="monitoring-events"),
    path("monitoring/events/<int:event_id>/", views.monitoring_event_detail_page, name="monitoring-event-detail"),
    # ── API ──────────────────────────────────────────────
    path("api/menu/", views.MenuView.as_view(), name="api-menu"),
    path(
        "api/safety-status/",
        views.MySafetyStatusView.as_view(),
        name="api-safety-status",
    ),
    path(
        "api/refresh/",
        views.DashboardRefreshView.as_view(),
        name="api-dashboard-refresh",
    ),
]
