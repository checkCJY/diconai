# monitoring/models/power_event.py
from django.core.exceptions import ValidationError
from django.db import models


class PowerEvent(models.Model):
    """
    16채널 ON/OFF 상태 스냅샷 — 이벤트성 기록

    [snapshot 스키마]
    {"1": true, "2": false, "3": true, ..., "16": false}
    키: 채널 번호 (문자열 "1"~"16", 1-based)
    값: ON(true) / OFF(false)
    수신 시 validate_snapshot()으로 검증 후 저장

    [changed_channels 스키마]
    이번 이벤트에서 상태가 바뀐 채널 번호 목록 (1-based 정수)
    예시: [3, 7, 12] — ch3, ch7, ch12가 이번에 변경됨
    None: 최초 수신(이전 스냅샷 없음)
    []: 이전 스냅샷 대비 변경 없음

    [trigger 정책]
    manual        : 관리자 수동 조작
    alarm_auto    : 알람 임계치 초과로 자동 차단
    recovery_auto : 자동 복구
    power_cut     : 전원 차단 (장비 OFFLINE 후 재연결)
    unknown       : 원인 불명 (파싱 실패 또는 미분류)

    [PowerData와의 차이]
    PowerData: 주기적 측정값 (전류/전압/전력 수치)
    PowerEvent: 상태 변경 순간 스냅샷 (ON/OFF) — 이벤트성
    """

    class Trigger(models.TextChoices):
        MANUAL = "manual", "수동 조작"
        ALARM_AUTO = "alarm_auto", "알람 자동 차단"
        RECOVERY_AUTO = "recovery_auto", "자동 복구"
        POWER_CUT = "power_cut", "전원 차단"
        UNKNOWN = "unknown", "원인 불명"

    power_device = models.ForeignKey(
        "facilities.PowerDevice",
        on_delete=models.PROTECT,  # 장비 삭제 차단 — 이벤트 이력 보존
        related_name="power_events",
    )

    # 전체 채널 ON/OFF 상태를 원자적으로 저장 (이벤트 발생 시점의 전체 상태)
    snapshot = models.JSONField(verbose_name="16채널 상태 스냅샷")

    # None: 최초 수신(비교 대상 없음) / []: 변경 없음 / [3, 7]: ch3, ch7 변경
    changed_channels = models.JSONField(
        null=True,
        blank=True,
        verbose_name="변경된 채널 번호 리스트",
    )

    trigger = models.CharField(
        max_length=20,
        choices=Trigger.choices,
        default=Trigger.UNKNOWN,
        verbose_name="이벤트 원인",
    )

    # 장치 측정 시각 — PowerData.measured_at과 JOIN 기준 통일
    # null=True: 0002 마이그레이션 이전 기존 row 호환
    measured_at = models.DateTimeField(verbose_name="측정 시각")
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def validate_snapshot(data: dict) -> None:
        """
        snapshot JSON 구조 검증
        - 키: "1"~"16" 문자열 (1-based 채널 번호)
        - 값: bool (True=ON, False=OFF)
        """
        if not isinstance(data, dict):
            raise ValidationError("snapshot은 dict 형식이어야 합니다.")
        for key, val in data.items():
            if not key.isdigit() or not (1 <= int(key) <= 16):
                raise ValidationError(
                    f"잘못된 채널 키: '{key}' — 1~16 범위의 문자열이어야 합니다."
                )
            if not isinstance(val, bool):
                raise ValidationError(
                    f"채널 {key}의 값은 bool이어야 합니다. 받은 값: {val!r}"
                )

    def clean(self):
        self.validate_snapshot(self.snapshot)

    @property
    def on_channels(self) -> list[int]:
        """현재 스냅샷에서 ON 상태인 채널 번호 목록"""
        if not self.snapshot:
            return []
        return [int(k) for k, v in self.snapshot.items() if v is True]

    @property
    def off_channels(self) -> list[int]:
        """현재 스냅샷에서 OFF 상태인 채널 번호 목록"""
        if not self.snapshot:
            return []
        return [int(k) for k, v in self.snapshot.items() if v is False]

    class Meta:
        db_table = "power_event"
        indexes = [
            models.Index(
                fields=["power_device", "-created_at"],
                name="idx_power_event_device_time",
            ),
            # PowerData.measured_at과 시간 범위 JOIN 시 사용
            models.Index(
                fields=["power_device", "-measured_at"],
                name="idx_pwr_evt_dev_meas",
            ),
            # trigger 인덱스 제거 — 실제 쿼리 패턴에 없음, write 비용만 증가
        ]
