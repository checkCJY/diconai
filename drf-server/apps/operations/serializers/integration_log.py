from rest_framework import serializers

from apps.operations.models import IntegrationLog


class IntegrationLogCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationLog
        fields = [
            "integration_type",
            "target_system",
            "result",
            "description",
            "extra",
        ]
