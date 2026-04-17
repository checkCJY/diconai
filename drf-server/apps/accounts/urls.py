from django.shortcuts import render
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views


def login_page(request):
    return render(request, "auth/login.html")


urlpatterns = [
    # ── HTML 페이지 ──────────────────────────────────────
    path("login/", login_page, name="login"),
    # ── API ──────────────────────────────────────────────
    path("api/auth/login/", views.LoginView.as_view(), name="api-login"),
    path("api/auth/me/", views.MeView.as_view(), name="api-me"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
