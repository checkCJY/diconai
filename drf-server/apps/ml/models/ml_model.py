# apps/ml/models/ml_model.py
from django.db import models


class MLModel(models.Model):
    """
    학습된 ML 모델의 메타데이터.

    학습 1회 = MLModel row 1건 + .pkl 파일 1개.
    .pkl 파일 실체는 settings.ML_MODELS_DIR 아래 저장 (MEDIA_ROOT 밖, 웹 서빙 차단).

    [매칭 단위]
    sensor_identifier 로 단일 시계열 모델(ARIMA 등)을 식별한다. 빈 문자열이면
    sensor_type 단위 공유 (IF 기본 동작). 활성 모델은 (sensor_type, algorithm,
    sensor_identifier) 단위로 1건만 허용 (Meta constraints).
    """

    class Algorithm(models.TextChoices):
        ISOLATION_FOREST = "isolation_forest", "Isolation Forest"
        ARIMA = "arima", "ARIMA"

    class SensorType(models.TextChoices):
        POWER = "power", "전력"
        GAS = "gas", "가스"

    version = models.PositiveIntegerField(
        verbose_name="모델 버전",
        help_text=(
            "동일 (sensor_type, algorithm, sensor_identifier) 안에서 1부터 순차 증가"
        ),
    )
    sensor_type = models.CharField(
        max_length=10,
        choices=SensorType.choices,
        verbose_name="센서 종류",
    )
    algorithm = models.CharField(
        max_length=30,
        choices=Algorithm.choices,
        default=Algorithm.ISOLATION_FOREST,
        verbose_name="모델 알고리즘",
    )
    sensor_identifier = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="센서 식별자",
        help_text=(
            "ARIMA 등 단일 시계열 모델용. 예: 'power:device_1:ch3:watt'. "
            "비어 있으면 sensor_type 단위 (전 sensor 공유)."
        ),
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
        help_text=(
            "추론에 사용할 모델 1개당 1건만 True "
            "((sensor_type, algorithm, sensor_identifier) 단위)"
        ),
    )

    def __str__(self) -> str:
        sid = f":{self.sensor_identifier}" if self.sensor_identifier else ""
        return f"{self.sensor_type}{sid} v{self.version} ({self.algorithm})"

    class Meta:
        db_table = "ml_model"
        constraints = [
            models.UniqueConstraint(
                fields=["sensor_type", "algorithm", "sensor_identifier", "version"],
                name="uq_ml_model_sensor_alg_id_version",
            ),
            # 활성 모델 1건 제약 — (sensor_type, algorithm, sensor_identifier) 단위.
            # IF (sensor_identifier="") 와 ARIMA (sensor_identifier="power:..." 등) 가
            # 같은 sensor_type 안에서 각각 1건씩 활성 가능.
            models.UniqueConstraint(
                fields=["sensor_type", "algorithm", "sensor_identifier"],
                condition=models.Q(is_active=True),
                name="uq_ml_model_active_per_match_unit",
            ),
        ]
        indexes = [
            models.Index(
                fields=["sensor_type", "is_active"],
                name="idx_ml_model_active",
            ),
            models.Index(fields=["-trained_at"], name="idx_ml_model_trained"),
        ]
