from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # ── 관리자 ───────────────────────────────────────────
    path("admin/", admin.site.urls),
    # ── 루트 → 대시보드 리다이렉트 ──────────────────────
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    # ── 앱별 라우팅 ──────────────────────────────────────
    path("accounts/", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("alarms/", include("apps.alarms.urls")),
]
