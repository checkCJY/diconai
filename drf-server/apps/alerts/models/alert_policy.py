from django.db import models

from apps.core.constants import AlarmType
from apps.core.models.base import BaseModel


class AlertPolicy(BaseModel):
    """
    알림 정책 — "어떤 이벤트가 누구에게 어떤 채널로 알림"

    [target_user_types JSON]
    lowercase user_type 배열 (예: ["facility_admin", "worker"]).
    정밀 추적 요구 발생 시 RoleProfile FK/M2M으로 마이그레이션 가능.

    [target_facility=NULL]
    NULL이면 전사 정책. 특정 facility 지정 시 해당 공장에만 적용.

    [condition_summary]
    목록 화면 캐시 컬럼. service 레이어(policy_matcher)에서 갱신.
    save() 오버라이드 안 함 — 컨벤션(view → service → model) 유지.

    [event_type vs USER_FACING_ALARM_TYPES]
    AlarmType.choices 전체를 사용 가능 (모델 레벨). 단 화면에서는 SENSOR_FAULT 제외 9종만
    노출 — 프론트는 USER_FACING_ALARM_TYPES 참조.
    """

    class PolicyKind(models.TextChoices):
        STATEFUL = "stateful", "상태 기반"
        IMMEDIATE = "immediate", "즉시"
        SCHEDULED = "scheduled", "예정"

    name = models.CharField(max_length=100)
    event_type = models.CharField(
        max_length=50,
        choices=AlarmType.choices,
        verbose_name="대상 이벤트",
    )
    policy_kind = models.CharField(
        max_length=20,
        choices=PolicyKind.choices,
        default=PolicyKind.IMMEDIATE,
    )
    target_facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alert_policies",
        help_text="NULL이면 전사 정책",
    )
    target_user_types = models.JSONField(
        default=list,
        help_text='lowercase user_type 배열, 예: ["facility_admin", "worker"]',
    )
    target_sensor_ids = models.JSONField(default=list, blank=True)
    target_device_ids = models.JSONField(default=list, blank=True)
    target_geofence_ids = models.JSONField(default=list, blank=True)
    channels = models.JSONField(
        default=list,
        help_text='Notification.Channel.values 부분집합, 예: ["popup", "sms"]',
    )
    condition_summary = models.CharField(
        max_length=300,
        blank=True,
        default="",
        help_text="목록 화면 캐시 — service 레이어에서 갱신",
    )
    # Notification.message 렌더 템플릿 (Django Template 문법).
    # 예: "{{ source_label }}에서 {% if level == 'danger' %}🚨 긴급{% else %}⚠️ 주의{% endif %} — {{ gas_name }} {{ value }}{{ unit }}"
    # 빈 문자열이면 Event.summary를 그대로 사용 (graceful fallback).
    message_template = models.TextField(
        blank=True,
        default="",
        verbose_name="알림 메시지 템플릿",
        help_text="Django Template 문법. 빈 값이면 Event.summary 사용",
    )
    recommended_actions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="권고 조치",
        help_text=(
            "risk_level별 단계 리스트. "
            '예: {"danger": [...], "warning": [...]} 또는 {"default": [...]}'
        ),
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.name} ({self.event_type})"

    class Meta:
        db_table = "alert_policy"
        indexes = [
            models.Index(
                fields=["event_type", "is_active"], name="idx_policy_event_active"
            ),
            models.Index(
                fields=["target_facility", "is_active"], name="idx_policy_fac_active"
            ),
        ]
