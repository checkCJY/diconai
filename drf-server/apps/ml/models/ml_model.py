# apps/ml/models/ml_model.py
from django.db import models


class MLModel(models.Model):
    """
    학습된 ML 모델의 메타데이터.

    학습 1회 = MLModel row 1건 + .pkl 파일 1개.
    .pkl 파일 실체는 settings.ML_MODELS_DIR 아래 저장 (MEDIA_ROOT 밖, 웹 서빙 차단).
    """

    class ModelType(models.TextChoices):
        ISOLATION_FOREST = "isolation_forest", "Isolation Forest"

    class SensorType(models.TextChoices):
        POWER = "power", "전력"
        GAS = "gas", "가스"

    version = models.PositiveIntegerField(
        verbose_name="모델 버전",
        help_text="동일 sensor_type 안에서 1부터 순차 증가",
    )
    sensor_type = models.CharField(
        max_length=10,
        choices=SensorType.choices,
        verbose_name="센서 종류",
    )
    model_type = models.CharField(
        max_length=30,
        choices=ModelType.choices,
        default=ModelType.ISOLATION_FOREST,
        verbose_name="모델 타입",
    )
    trained_at = models.DateTimeField(auto_now_add=True, verbose_name="학습 완료 시각")
    file_path = models.CharField(
        max_length=255,
        verbose_name=".pkl 파일 경로",
        help_text="settings.ML_MODELS_DIR 기준 상대 경로",
    )
    training_data_range_from = models.DateTimeField(
        verbose_name="학습 데이터 시작",
    )
    training_data_range_to = models.DateTimeField(
        verbose_name="학습 데이터 끝",
    )
    training_sample_count = models.PositiveIntegerField(
        verbose_name="학습 샘플 수",
        help_text="윈도우 적용 전 raw row 수",
    )
    feature_columns = models.JSONField(
        verbose_name="피처 컬럼",
        help_text="학습에 사용된 컬럼 이름 리스트 (추론 시 동일 순서로 입력)",
    )
    params_json = models.JSONField(
        verbose_name="학습 하이퍼파라미터",
        help_text="contamination, n_estimators 등",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="활성 모델",
        help_text="추론에 사용할 모델 1개당 1건만 True (sensor_type 별로)",
    )

    def __str__(self) -> str:
        return f"{self.sensor_type} v{self.version} ({self.model_type})"

    class Meta:
        db_table = "ml_model"
        constraints = [
            models.UniqueConstraint(
                fields=["sensor_type", "version"],
                name="uq_ml_model_sensor_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["sensor_type", "is_active"],
                name="idx_ml_model_active",
            ),
            models.Index(fields=["-trained_at"], name="idx_ml_model_trained"),
        ]
