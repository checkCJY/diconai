# apps/ml/views.py
"""
ML 모델 메타데이터 API.

운영 흐름:
- drf-server: 학습 + MLModel row 관리 (단일 진실 공급원)
- fastapi-server: GET /api/ml/models/active/?sensor_type=power 로 active 모델 메타 조회 후 .pkl 로드
"""

from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView

from apps.ml.models import MLModel


class _ActiveMLModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MLModel
        fields = (
            "id",
            "version",
            "sensor_type",
            "model_type",
            "file_path",
            "feature_columns",
            "params_json",
            "training_data_range_from",
            "training_data_range_to",
            "training_sample_count",
            "trained_at",
        )


class ActiveMLModelView(RetrieveAPIView):
    """
    sensor_type 의 활성 ML 모델 메타 조회.

    GET /api/ml/models/active/?sensor_type=power
    """

    serializer_class = _ActiveMLModelSerializer
    permission_classes: list = []  # 내부 API. fastapi 만 접근. 추후 INTERNAL_SERVICE_TOKEN 권장.

    def get_object(self):
        sensor_type = self.request.query_params.get("sensor_type")
        if sensor_type not in ("power", "gas"):
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"sensor_type": "must be power|gas"})
        obj = MLModel.objects.filter(sensor_type=sensor_type, is_active=True).first()
        if obj is None:
            from django.http import Http404

            raise Http404(f"no active model for sensor_type={sensor_type}")
        return obj
