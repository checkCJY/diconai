# apps/ml/models/ml_anomaly_result.py
from django.db import models


class MLAnomalyResult(models.Model):
    """
    IF 추론 결과 — 1 추론 = 1 row.

    PowerData/GasData 와는 측정값 ID로 직접 FK 안 걸고, sensor_identifier 문자열로 연결.
    이유: 가스/전력 외 센서 추가 시 스키마 변경 없이 확장 가능 + 측정값 row 삭제와 분리.
    """

    class Prediction(models.TextChoices):
        NORMAL = "normal", "정상"
        ANOMALY = "anomaly", "이상"

    class RiskClassified(models.TextChoices):
        # fastapi combine_risk_5axis 와 vocab 동기화 필수. "warning" 은 3축
        # 매트릭스에서 정적 임계 + AI 신호 부분 동의 시 격상값 — 누락 시 forward 400.
        NORMAL = "normal", "정상"
        CAUTION = "caution", "주의"
        PREDICT_WARN = "predict_warn", "예측경고"
        WARNING = "warning", "경고"
        DANGER = "danger", "위험"

    ml_model = models.ForeignKey(
        "ml.MLModel",
        on_delete=models.SET_NULL,
        null=True,
        related_name="anomaly_results",
        verbose_name="추론 모델",
    )
    model_version_snapshot = models.PositiveIntegerField(
        verbose_name="모델 버전 (스냅샷)",
        help_text="MLModel 삭제되더라도 추론 시점 버전 보존",
    )
    sensor_type = models.CharField(
        max_length=10,
        verbose_name="센서 종류",
        help_text="power / gas — MLModel.SensorType 값 사용",
    )
    sensor_identifier = models.CharField(
        max_length=64,
        verbose_name="센서 식별자",
        help_text="예: 'power:device_1:ch3:watt' 또는 'gas:co'",
    )
    measured_at = models.DateTimeField(verbose_name="측정 시각")
    evaluated_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="추론 실행 시각",
    )
    anomaly_score = models.FloatField(
        verbose_name="이상도 점수",
        help_text="IF decision_function 또는 score_samples 결과 (음수=이상)",
    )
    prediction = models.CharField(
        max_length=10,
        choices=Prediction.choices,
        verbose_name="이상 여부",
    )
    risk_classified = models.CharField(
        max_length=20,
        choices=RiskClassified.choices,
        default=RiskClassified.NORMAL,
        verbose_name="결합 위험도",
        help_text="결합 매트릭스로 임계치 평가와 AI 신호를 합친 분류",
    )
    feature_snapshot_json = models.JSONField(
        verbose_name="입력 피처 스냅샷",
        help_text="추론 시 사용된 피처 값 (디버깅·재현용)",
    )

    def __str__(self) -> str:
        return f"{self.sensor_identifier} @ {self.measured_at} → {self.prediction}"

    class Meta:
        db_table = "ml_anomaly_result"
        indexes = [
            models.Index(
                fields=["sensor_identifier", "-measured_at"],
                name="idx_ml_res_sensor_time",
            ),
            models.Index(
                fields=["prediction", "-measured_at"],
                name="idx_ml_res_pred_time",
            ),
            models.Index(fields=["-evaluated_at"], name="idx_ml_res_eval"),
        ]
