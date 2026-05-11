from django.db import models


class AppLog(models.Model):
    """
    운영 로그 — Python logging.error/warning 등을 영속화

    [SystemLog와의 분리]
    SystemLog는 사용자 감사 로그 (actor 필수). AppLog는 운영 로그 (actor 없음).
    책임 분리로 인덱스/보관 정책 독립.

    [APPEND-ONLY]
    save() / delete() 차단. SystemLog와 동일 패턴.

    [Phase 2 시점]
    DBLogHandler가 동기 INSERT (운영 부하 측정 후 Phase 4에서 비동기/batch 검토).
    재귀 가드는 핸들러에서 처리.
    """

    class LogCategory(models.TextChoices):
        ERROR = "error", "오류"
        BATCH = "batch", "배치"
        SERVICE = "service", "서비스"

    log_category = models.CharField(
        max_length=20, choices=LogCategory.choices, verbose_name="로그 분류"
    )
    service_module = models.CharField(
        max_length=100,
        verbose_name="서비스 모듈",
        help_text='예: "celery.tasks.fire_alarm", "apps.alerts.services"',
    )
    level = models.CharField(
        max_length=10, verbose_name="로그 레벨", help_text="ERROR/WARNING/INFO"
    )
    message = models.TextField()
    extra = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("AppLog는 수정할 수 없습니다. APPEND-ONLY 정책.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AppLog는 삭제할 수 없습니다.")

    class Meta:
        db_table = "app_log"
        indexes = [
            models.Index(
                fields=["log_category", "-created_at"], name="idx_applog_cat_time"
            ),
            models.Index(fields=["-created_at"], name="idx_applog_time"),
        ]
