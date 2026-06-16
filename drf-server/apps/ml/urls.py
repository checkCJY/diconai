# apps/ml/urls.py
from django.urls import path

from apps.ml.views import ActiveMLModelView, MLAnomalyResultCreateView


urlpatterns = [
    path("models/active/", ActiveMLModelView.as_view(), name="ml-active-model"),
    path(
        "anomaly-results/",
        MLAnomalyResultCreateView.as_view(),
        name="ml-anomaly-result-create",
    ),
]
