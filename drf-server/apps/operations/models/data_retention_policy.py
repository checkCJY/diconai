from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import BaseModel


class DataRetentionPolicy(BaseModel):
    """
    데이터 보관 정책 — 가스/전력/위치 시계열 데이터 자동 정리

    [횡단 책임]
    monitoring(GasData/PowerData) + positioning(WorkerPosition)을 모두 다룸 →
    operations 앱에 배치 (특정 도메인 앱에 종속되지 않음).

    [실행]
    Phase 4-g에서 Celery 보관 배치 태스크가 본 모델을 순회하며 실제 삭제 수행.
    Phase 1은 모델만 신설.

    [clean()]
    history_retention_days >= raw_retention_days 강제 — 이력은 원천보다 오래 보관.
    """

    class DeviceType(models.TextChoices):
        GAS_SENSOR = "gas_sensor", "유해가스 센서"
        POWER = "power", "전력"
        POSITION_NODE = "position_node", "위치 노드"
        # AI/ML 모델·추론 결과 (sensor 종류와 무관한 시스템 자산)
        ML = "ml", "AI/ML"
        # 로그·알림 등 도메인 횡단 시스템 데이터
        SYSTEM = "system", "시스템"

    class DataCategory(models.TextChoices):
        # ── 센서 원천 ─────────────────────────────────────────────
        GAS_RAW = "gas_raw", "가스 원천 데이터"
        GAS_ANOMALY = "gas_anomaly", "가스 이상 이력"
        # GasDataHourly 집계 테이블 (Phase 4에서 모델 신설 예정)
        GAS_HOURLY = "gas_hourly", "가스 시간 집계"
        POWER_RAW = "power_raw", "전력 원천 데이터"
        POWER_AGG = "power_agg", "전력 집계 이력"
        # PowerDataHourly 집계 테이블 (Phase 4에서 모델 신설 예정)
        POWER_HOURLY = "power_hourly", "전력 시간 집계"
        POSITION_HIST = "position_hist", "위치 이력"
        # ── AI/ML ─────────────────────────────────────────────────
        # MLAnomalyResult (IF) + GasArimaResult (ARIMA) 통합 관리
        ML_RESULT = "ml_result", "AI 추론 결과"
        # MLModel DB행 + .pkl 파일 — is_active=False + raw_retention_days 초과 시 삭제
        ML_MODEL = "ml_model", "AI 모델 파일"
        # ── 시스템 로그 ───────────────────────────────────────────
        # SystemLog: 시스템·사용자활동·지도편집 로그 통합 테이블
        SYSTEM_LOG = "system_log", "시스템 로그"
        # IntegrationLog: FastAPI→DRF 연동 호출 기록
        INTEGRATION_LOG = "integration_log", "연동 로그"
        # AppLog: Python logging.error/warning 영속화
        APP_LOG = "app_log", "앱 로그"
        # LoginLog: 로그인·로그아웃 이력
        LOGIN_LOG = "login_log", "로그인 로그"
        # Notification: 발송 이력 (popup/push/sms/email)
        NOTIFICATION = "notification", "알림 이력"

    class DeleteCycle(models.TextChoices):
        DAILY = "daily", "매일"
        MONTHLY_1 = "monthly_1", "매월 1일"
        MONTHLY_15 = "monthly_15", "매월 15일"
        MONTHLY_LAST = "monthly_last", "매월 말일"
        QUARTERLY = "quarterly", "분기 말"

    device_type = models.CharField(
        max_length=20, choices=DeviceType.choices, verbose_name="장비 유형"
    )
    data_category = models.CharField(
        max_length=20, choices=DataCategory.choices, verbose_name="데이터 분류"
    )
    raw_retention_days = models.PositiveIntegerField(
        default=30, verbose_name="원천 보관 기간(일)"
    )
    history_retention_days = models.PositiveIntegerField(
        default=180, verbose_name="이력 보관 기간(일)"
    )
    delete_cycle = models.CharField(
        max_length=20,
        choices=DeleteCycle.choices,
        default=DeleteCycle.DAILY,
        verbose_name="삭제 주기",
    )
    is_active = models.BooleanField(default=True)
    memo = models.TextField(blank=True, default="")
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retention_policies",
        verbose_name="담당자",
    )

    def clean(self):
        if self.history_retention_days < self.raw_retention_days:
            raise ValidationError("이력 보관 기간은 원천 보관 기간 이상이어야 합니다.")

    def __str__(self):
        return f"{self.get_device_type_display()} / {self.get_data_category_display()}"

    class Meta:
        db_table = "data_retention_policy"
        constraints = [
            models.UniqueConstraint(
                fields=["device_type", "data_category"],
                name="uq_retention_device_category",
            ),
        ]
        ordering = ["device_type", "data_category"]
