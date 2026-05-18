# apps/ml/views.py
"""
ML 모델 메타데이터 + 추론 결과 저장 API.

운영 흐름:
- drf-server: 학습 + MLModel row 관리 (단일 진실 공급원) + 추론 결과 저장
- fastapi-server: GET /api/ml/models/active/?sensor_type=power 로 active 모델 메타 조회 후 .pkl 로드
- T1 추론 트리거 (별도 작업): fastapi 추론 → combine_risk → POST /api/ml/anomaly-results/
"""

from rest_framework import serializers
from rest_framework.generics import CreateAPIView, RetrieveAPIView

from apps.ml.models import MLAnomalyResult, MLModel


class _ActiveMLModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MLModel
        fields = (
            "id",
            "version",
            "sensor_type",
            "algorithm",
            "sensor_identifier",
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
    (sensor_type, algorithm, sensor_identifier) 매칭 단위 활성 ML 모델 메타 조회.

    GET /api/ml/models/active/?sensor_type=power
      → 기본값 algorithm=isolation_forest, sensor_identifier="" 매칭 (기존 IF 회귀 0)
    GET /api/ml/models/active/?sensor_type=power&algorithm=arima
        &sensor_identifier=power:device_1:ch1:watt
      → ARIMA 단일 시계열 모델 매칭 (W2.5 학습 결과)
    """

    serializer_class = _ActiveMLModelSerializer
    # 내부 API. fastapi 만 접근. 추후 INTERNAL_SERVICE_TOKEN 권장.
    # authentication_classes=[] — drf_client 가 부착하는 invalid Bearer 토큰을
    # JWTAuthentication 이 401 처리하지 않도록 인증 자체 skip.
    authentication_classes: list = []
    permission_classes: list = []

    def get_object(self):
        from rest_framework.exceptions import ValidationError

        params = self.request.query_params
        sensor_type = params.get("sensor_type")
        algorithm = params.get("algorithm", MLModel.Algorithm.ISOLATION_FOREST.value)
        sensor_identifier = params.get("sensor_identifier", "")

        if sensor_type not in ("power", "gas"):
            raise ValidationError({"sensor_type": "must be power|gas"})
        if algorithm not in MLModel.Algorithm.values:
            raise ValidationError(
                {"algorithm": f"must be one of {MLModel.Algorithm.values}"}
            )

        obj = MLModel.objects.filter(
            sensor_type=sensor_type,
            algorithm=algorithm,
            sensor_identifier=sensor_identifier,
            is_active=True,
        ).first()
        if obj is None:
            from django.http import Http404

            raise Http404(
                f"no active model for sensor_type={sensor_type} "
                f"algorithm={algorithm} sensor_identifier={sensor_identifier!r}"
            )
        return obj


class _MLAnomalyResultCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MLAnomalyResult
        fields = (
            "id",
            "ml_model",
            "model_version_snapshot",
            "sensor_type",
            "sensor_identifier",
            "measured_at",
            "anomaly_score",
            "prediction",
            "risk_classified",
            "feature_snapshot_json",
        )
        read_only_fields = ("id",)


class MLAnomalyResultCreateView(CreateAPIView):
    """
    IF 추론 결과 저장.

    POST /api/ml/anomaly-results/
    Body: ml_model, model_version_snapshot, sensor_type, sensor_identifier,
          measured_at, anomaly_score, prediction, risk_classified, feature_snapshot_json
    Returns: 201 + 생성된 row

    호출자 (T1-6 추론 트리거): fastapi /predict 응답을 받아 threshold_risk 와 함께
    combine_risk 계산 후 risk_classified 채워서 POST. 본 view 는 단순 INSERT 만 담당.
    """

    queryset = MLAnomalyResult.objects.all()
    serializer_class = _MLAnomalyResultCreateSerializer
    # 내부 API. fastapi 만 접근. 추후 INTERNAL_SERVICE_TOKEN 권장.
    # authentication_classes=[] — drf_client 가 부착하는 invalid Bearer 토큰을
    # JWTAuthentication 이 401 처리하지 않도록 인증 자체 skip.
    authentication_classes: list = []
    permission_classes: list = []
