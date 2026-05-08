# notifications/models/notification.py
from django.conf import settings
from django.db import models

from apps.core.constants import RiskLevel
from apps.core.models.base import BaseModel


class Notification(BaseModel):
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

    # Phase 3-e: CASCADE → SET_NULL + nullable.
    # 이유: 점검 일정/배치 실패 등 비-Event 알림 허용. Event 삭제 시 알림 이력 보존.
    # clean()에서 event/policy 중 하나는 필수로 강제.
    event = models.ForeignKey(
        "alerts.Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name="원천 이벤트",
    )
    # Phase 3-e: 트리거 정책 추적. Event 없는 알림(점검 사전 알림 등)도 policy로 추적 가능.
    # AlertPolicy 비활성/삭제 시 SET_NULL.
    policy = models.ForeignKey(
        "alerts.AlertPolicy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name="트리거 정책",
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
    # Phase 3-e: 재시도 추적. retry_count는 발송 시도 횟수 (initial 0).
    retry_count = models.PositiveIntegerField(default=0, verbose_name="재시도 횟수")
    # Phase 3-e: created_at(생성)과 분리. last_attempted_at은 최근 발송 시도 시각.
    # NULL = 시도 전. (now - last_attempted_at > NOTIFICATION_DELAY_THRESHOLD_MINUTES) 이면 화면 "지연" 라벨.
    last_attempted_at = models.DateTimeField(
        null=True, blank=True, verbose_name="최근 발송 시도 시각"
    )

    # is_read는 3차 레거시 — 개인 알림용
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    # created_at / updated_at / updated_by 는 BaseModel 상속

    def mark_as_read(self):
        """알림 읽음 처리"""
        from django.utils import timezone

        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    def clean(self):
        """
        검증:
        1. target_user와 is_broadcast 상호 배타 (개인 vs 브로드캐스트)
        2. event/policy 중 하나는 필수 — Phase 3-e (출처 없는 알림 차단)
        """
        from django.core.exceptions import ValidationError

        if self.is_broadcast and self.target_user is not None:
            raise ValidationError(
                "is_broadcast=True일 때 target_user는 NULL이어야 합니다."
            )
        if not self.is_broadcast and self.target_user is None:
            raise ValidationError("개인 알림은 target_user가 필수입니다.")
        if self.event_id is None and self.policy_id is None:
            raise ValidationError(
                "Notification은 event 또는 policy 중 하나는 필수입니다."
            )

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
