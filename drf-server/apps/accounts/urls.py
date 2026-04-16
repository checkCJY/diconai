from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="api-login"),
    path("me/", views.MeView.as_view(), name="api-me"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
