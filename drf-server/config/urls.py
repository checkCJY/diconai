from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.accounts.urls import api_urlpatterns as auth_api_urlpatterns
from apps.accounts.urls import page_urlpatterns as auth_page_urlpatterns


urlpatterns = [
    # ── 관리자 ───────────────────────────────────────────
    path("admin/", admin.site.urls),
    # ── 루트 → 대시보드 리다이렉트 ──────────────────────
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    # ── 앱별 라우팅 ──────────────────────────────────────
    path("accounts/", include(auth_page_urlpatterns)),  # HTML: /accounts/login/
    path(
        "api/auth/", include(auth_api_urlpatterns)
    ),  # API:  /api/auth/login/, /api/auth/me/
    path("dashboard/", include("apps.dashboard.urls")),
    path("alerts/", include("apps.alerts.urls")),
    path("positioning/", include("apps.positioning.urls")),
]
