# apps/ml/urls.py
from django.urls import path

from apps.ml.views import ActiveMLModelView


urlpatterns = [
    path("models/active/", ActiveMLModelView.as_view(), name="ml-active-model"),
]
