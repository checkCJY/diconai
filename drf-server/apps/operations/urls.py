from django.urls import path

from apps.operations.views.internal.integration_log import (
    IntegrationLogInternalCreateView,
)

app_name = "operations"

urlpatterns = [
    path(
        "internal/integration-logs/",
        IntegrationLogInternalCreateView.as_view(),
        name="internal-integration-log-create",
    ),
]
