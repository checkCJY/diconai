from django.shortcuts import render
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views
from apps.core.constants import CONTACT_INFO


def login_page(request):
    return render(request, "auth/login.html", {"contact_info": CONTACT_INFO})


# HTML 페이지 라우팅 (config/urls.py에서 "accounts/" 프리픽스로 포함)
page_urlpatterns = [
    path("login/", login_page, name="login"),
]

# API 라우팅 (config/urls.py에서 "api/auth/" 프리픽스로 포함)
api_urlpatterns = [
    path("login/", views.LoginView.as_view(), name="api-login"),
    path("me/", views.MeView.as_view(), name="api-me"),
    path("profile/", views.MyProfileView.as_view(), name="api-profile"),
    path(
        "password/change/",
        views.PasswordChangeView.as_view(),
        name="api-password-change",
    ),
    path("logout/", views.LogoutView.as_view(), name="api-logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]

urlpatterns = page_urlpatterns + api_urlpatterns
