# alerts/models/event_log.py
from django.conf import settings
from django.db import models

from core.constants import EventStatus


# `EventLog.objects.filter(...).delete()`를 실행할 경우 에러 없이 삭제되어 무결성 방지용.
class EventLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("EventLog는 Bulk Update가 불가능한 APPEND-ONLY 모델입니다.")

    def delete(self):
        raise ValueError("EventLog는 Bulk Delete가 불가능한 APPEND-ONLY 모델입니다.")


class EventLogManager(models.Manager):
    def get_queryset(self):
        return EventLogQuerySet(self.model, using=self._db)


class EventLog(models.Model):
    """
    Event 처리 이력 — APPEND-ONLY 감사 로그

    [APPEND-ONLY 정책]
    save() / delete() 오버라이드로 수정·삭제 차단
    4차에 PostgreSQL 트리거로 DB 레벨 강제 예정


    [Action 유형]
    CREATED        : Event 생성됨
    CONFIRMED      : 관리자 확인 (active → acknowledged)
    STATUS_CHANGED : 일반 상태 변경
    NOTE_ADDED     : 메모만 추가 (상태 변경 없음)
    RESOLVED       : 조치 완료 (* → resolved)

    [actor 정책]
    actor: SET_NULL — 관리자 탈퇴해도 이력 보존
    actor=NULL은 "탈퇴 관리자의 과거 조치"를 의미
    """

    objects = EventLogManager()  # 커스텀 매니저 연결

    class Action(models.TextChoices):
        CREATED = "created", "생성"
        CONFIRMED = "confirmed", "확인"
        STATUS_CHANGED = "status_changed", "상태 변경"
        NOTE_ADDED = "note_added", "메모 추가"
        RESOLVED = "resolved", "완료"

    event = models.ForeignKey(
        "alerts.Event", on_delete=models.CASCADE, related_name="logs"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_logs",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    previous_status = models.CharField(
        max_length=20, choices=EventStatus.choices, blank=True, default=""
    )
    new_status = models.CharField(
        max_length=20, choices=EventStatus.choices, blank=True, default=""
    )
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("EventLog는 수정할 수 없습니다. APPEND-ONLY 정책.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("EventLog는 삭제할 수 없습니다.")

    class Meta:
        db_table = "event_log"
        indexes = [
            models.Index(
                fields=["event", "created_at"], name="idx_event_log_event_time"
            ),
            models.Index(
                fields=["actor", "-created_at"], name="idx_event_log_actor_time"
            ),
        ]
