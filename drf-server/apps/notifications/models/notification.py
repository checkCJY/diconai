# notifications/models/notification.py
from django.conf import settings
from django.db import models

from core.constants import RiskLevel


class Notification(models.Model):
    """
    알림 발송 레코드

    [v3 변경 — event 참조로 전환]
    v2의 alarm_id FK → event_id FK로 변경
    이유: 동일 위험 상황에서 AlarmRecord가 분당 수십 개 발생해도
    Event는 하나이므로 알림 스팸을 근본적으로 방지

    [수신자 정책]
    target_user: 특정 사용자에게 발송 (SET_NULL 허용)
    is_broadcast: True면 target_user 무시, 공장 전체에 발송
    둘 중 하나만 유효:
    - target_user=NOT NULL, is_broadcast=False → 개인 알림
    - target_user=NULL, is_broadcast=True → 브로드캐스트

    [delivery_status 생명주기]
    PENDING → SENT → DELIVERED
    실패 시: FAILED (재시도 대상)
    3차는 PENDING/SENT/FAILED만 사용, DELIVERED는 4차 WebSocket 도입 시

    [is_read의 한계]
    브로드캐스트 알림의 개별 수신자 읽음 상태 추적 불가
    → 4차 NotificationRead 모델 분리 예정 (로드맵 3.5)

    [severity]
    RiskLevel TextChoices 공유
    발송 채널 우선순위 결정: DANGER는 SMS 필수, WARNING은 팝업만 등
    """

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "발송 대기"
        SENT = "sent", "발송됨"
        DELIVERED = "delivered", "수신 확인"  # 4차
        FAILED = "failed", "발송 실패"

    class Channel(models.TextChoices):
        POPUP = "popup", "브라우저 팝업"
        PUSH = "push", "모바일 푸시"  # 4차
        SMS = "sms", "SMS"  # 4차
        EMAIL = "email", "이메일"  # 4차

    event = models.ForeignKey(
        "alerts.Event",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="원천 이벤트",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name="수신자 (개인 알림)",
    )
    is_broadcast = models.BooleanField(
        default=False, verbose_name="브로드캐스트 여부 (공장 전체)"
    )
    severity = models.CharField(
        max_length=10, choices=RiskLevel.choices, verbose_name="심각도"
    )
    channel = models.CharField(
        max_length=10, choices=Channel.choices, default=Channel.POPUP
    )
    title = models.CharField(max_length=200)
    message = models.TextField()

    delivery_status = models.CharField(
        max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    delivery_error = models.CharField(
        max_length=300, blank=True, default="", verbose_name="발송 실패 사유"
    )
    sent_at = models.DateTimeField(null=True, blank=True)

    # is_read는 3차 레거시 — 개인 알림용
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def mark_as_read(self):
        """알림 읽음 처리"""
        from django.utils import timezone

        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    def clean(self):
        """target_user와 is_broadcast 상호 배타 검증"""
        from django.core.exceptions import ValidationError

        if self.is_broadcast and self.target_user is not None:
            raise ValidationError(
                "is_broadcast=True일 때 target_user는 NULL이어야 합니다."
            )
        if not self.is_broadcast and self.target_user is None:
            raise ValidationError("개인 알림은 target_user가 필수입니다.")

    class Meta:
        db_table = "notification"
        indexes = [
            # 수신자별 미읽음 알림 조회
            models.Index(
                fields=["target_user", "is_read", "-created_at"],
                name="idx_notif_user_unread",
            ),
            # 이벤트별 알림 이력
            models.Index(fields=["event", "-created_at"], name="idx_notif_event_time"),
            # 발송 실패 재시도 대상
            models.Index(
                fields=["delivery_status", "-created_at"], name="idx_notif_status_time"
            ),
            # 브로드캐스트 미읽음
            models.Index(
                fields=["is_broadcast", "-created_at"],
                name="idx_notif_broadcast_time",
                condition=models.Q(is_broadcast=True),
            ),
        ]
