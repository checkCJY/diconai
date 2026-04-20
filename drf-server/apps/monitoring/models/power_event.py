# monitoring/models/power_event.py
from django.core.exceptions import ValidationError
from django.db import models


def validate_snapshot(data):
    """snapshot JSON 구조 검증"""
    if not isinstance(data, dict):
        raise ValidationError("snapshot은 dict 형식이어야 합니다.")
    expected_keys = set(str(i) for i in range(1, 17))  # 1~16 채널
    actual_keys = set(data.keys())
    if not actual_keys.issubset(expected_keys):
        raise ValidationError(
            f"snapshot 키는 1~16만 허용: {actual_keys - expected_keys}"
        )
    for ch, state in data.items():
        if not isinstance(state, bool):
            raise ValidationError(f"채널 {ch}의 상태는 boolean이어야 합니다.")


class PowerEvent(models.Model):
    """
    16채널 ON/OFF 상태 스냅샷 — 이벤트성 기록

    [snapshot 스키마]
    {"1": true, "2": false, "3": true, ..., "16": false}
    키: 채널 번호 (문자열 "1"~"16")
    값: ON(true) / OFF(false)
    수신 시 validate_snapshot()으로 검증

    [PowerData와의 차이]
    PowerData: 주기적 측정값 (전류/전압/전력 수치)
    PowerEvent: 상태 변경 순간 스냅샷 (ON/OFF)

    [변경 채널 추적]
    changed_channels: 이번 이벤트에서 상태가 바뀐 채널 번호 리스트
    이전 스냅샷과 비교해 수집 파이프라인에서 미리 계산
    """

    class Trigger(models.TextChoices):
        MANUAL_ADMIN = "manual_admin", "관리자 수동 조작"
        AUTO_ALARM = "auto_alarm", "알람 자동 차단"
        AUTO_RECOVERY = "auto_recovery", "자동 복구"
        POWER_OUTAGE = "power_outage", "전원 차단"
        UNKNOWN = "unknown", "원인 불명"

    power_device = models.ForeignKey(
        "facilities.PowerDevice", on_delete=models.PROTECT, related_name="power_events"
    )
    snapshot = models.JSONField(
        validators=[validate_snapshot], verbose_name="16채널 상태 스냅샷"
    )
    changed_channels = models.JSONField(
        default=list, blank=True, verbose_name="변경된 채널 번호 리스트"
    )
    trigger = models.CharField(
        max_length=20,
        choices=Trigger.choices,
        default=Trigger.UNKNOWN,
        verbose_name="이벤트 원인",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        validate_snapshot(self.snapshot)

    class Meta:
        db_table = "power_event"
        indexes = [
            models.Index(
                fields=["power_device", "-created_at"], name="idx_pwr_event_device_time"
            ),
            models.Index(
                fields=["trigger", "-created_at"], name="idx_pwr_event_trigger_time"
            ),
        ]
