from django.db import models


class IntegrationLog(models.Model):
    """
    연동 로그 — 시스템 간 호출 영속화 (FastAPI ↔ DRF, 외부 SMS/이메일 API 등)

    [APPEND-ONLY]
    SystemLog/AppLog와 동일 패턴.

    [Phase 2 시점]
    fire-and-forget 시작. raise_on_error=False로 본 흐름 비차단.
    부하 측정 후 Phase 4에서 batch flush 도입 검토 (모델 변경 없음).

    [target_system 형식 컨벤션]
    "<source>→<destination>"      예: "FastAPI→DRF"
    "<system>:<resource_id>"      예: "GasSensor:GS-001", "SMS:NCloud"
    자유 텍스트지만 위 두 패턴을 운영 컨벤션으로 권장 (Phase 2 §0-6).
    """

    class IntegrationType(models.TextChoices):
        COLLECT = "collect", "수집"
        TRANSMIT = "transmit", "전송"
        SYNC = "sync", "동기화"

    class Result(models.TextChoices):
        SUCCESS = "success", "성공"
        FAILURE = "failure", "실패"
        DELAY = "delay", "지연"

    integration_type = models.CharField(
        max_length=20, choices=IntegrationType.choices, verbose_name="연동 유형"
    )
    target_system = models.CharField(
        max_length=100,
        verbose_name="대상 시스템",
        help_text='형식: "FastAPI→DRF" 또는 "GasSensor:GS-001"',
    )
    result = models.CharField(max_length=10, choices=Result.choices)
    description = models.TextField(blank=True, default="")
    extra = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("IntegrationLog는 수정할 수 없습니다. APPEND-ONLY 정책.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("IntegrationLog는 삭제할 수 없습니다.")

    class Meta:
        db_table = "integration_log"
        indexes = [
            models.Index(
                fields=["integration_type", "-created_at"],
                name="idx_intlog_type_time",
            ),
            models.Index(
                fields=["result", "-created_at"], name="idx_intlog_result_time"
            ),
            models.Index(fields=["-created_at"], name="idx_intlog_time"),
        ]
