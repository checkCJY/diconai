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
    # 나중에 수정하게 될 부분
    path("positioning/", include("apps.positioning.urls")),
    path("monitoring/", include("apps.monitoring.urls_cjy")),
    # 관련 API는 관련 APPS로 넘어가서 수정
    path("api/", include("apps.geofence.urls")),
    path("api/positioning/", include("apps.positioning.urls")),
]
