# alerts/models/event.py
from django.conf import settings
from django.db import models

from apps.core.constants import AlarmType, EventStatus, RiskLevel


class Event(models.Model):
    """
    업무 워크플로우 단위 — 여러 AlarmRecord를 묶음

    [v3 신설 — 판정과 업무의 분리]
    AlarmRecord(자동 판정)와 Event(업무 워크플로우)를 별도 모델로 분리
    한 이벤트에 여러 AlarmRecord가 묶임 (N:1 관계)

    [병합 기준]
    병합 키: (source_sensor 또는 source_power_device 또는 source_geofence, event_type)
    활성 Event 존재 시: 기존 Event에 AlarmRecord만 추가, last_detected_at 업데이트
    활성 Event 없음: 새 Event 생성 + AlarmRecord 생성 + Notification 발송

    [발생원 FK]
    source_sensor, source_power_device, source_geofence 중 정확히 하나만 NOT NULL
    DB CHECK 제약으로 강제 (4차에 PostgreSQL CHECK 추가 예정)
    현재는 clean() 메서드와 Event 생성 서비스 로직으로 강제

    [source_label 캐시]
    발생 당시 장비/구역 이름을 문자열로 복사 저장
    나중에 장비 이름이 변경되어도 과거 이벤트 표시 일관성 유지
    기능정의서 CM-07의 "발생원" 필드 요구사항 대응

    [상태 전환]
    active → acknowledged → in_progress → resolved (일반 흐름)
    active → resolved (관리자 직접 완료)
    resolved 후 동일 조건 재발 시 새 Event 생성 (REOPEN 아님)
    """

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, related_name="events"
    )
    event_type = models.CharField(
        max_length=30, choices=AlarmType.choices, verbose_name="이벤트 유형"
    )
    risk_level = models.CharField(
        max_length=10, choices=RiskLevel.choices, verbose_name="위험도"
    )
    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.ACTIVE,
        verbose_name="상태",
    )

    # 발생원 FK (정확히 하나만 NOT NULL)
    source_sensor = models.ForeignKey(
        "facilities.GasSensor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events_as_source",
    )
    source_power_device = models.ForeignKey(
        "facilities.PowerDevice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events_as_source",
    )
    source_geofence = models.ForeignKey(
        "geofence.GeoFence",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events_as_source",
    )
    source_label = models.CharField(
        max_length=100, verbose_name="발생원 이름 캐시 (UI 표시용)"
    )

    # 연관 작업자
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events_as_worker",
    )

    summary = models.CharField(max_length=200, verbose_name="이벤트 요약")

    # 시간 추적
    first_detected_at = models.DateTimeField(verbose_name="최초 감지")
    last_detected_at = models.DateTimeField(verbose_name="마지막 감지")

    # 조치 추적
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events_acknowledged",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    last_notified_at = models.DateTimeField(
        null=True, blank=True, verbose_name="마지막 알림 발송 시각"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """발생원 FK 정확히 하나만 NOT NULL 강제"""
        from django.core.exceptions import ValidationError

        sources = [self.source_sensor, self.source_power_device, self.source_geofence]
        non_null = sum(1 for s in sources if s is not None)
        if non_null != 1:
            raise ValidationError(
                f"source_* FK 중 정확히 하나만 설정해야 합니다. 현재 {non_null}개"
            )

    class Meta:
        db_table = "event"
        indexes = [
            # 활성 이벤트 필터링 (대시보드 "조치필요/조치중" 탭)
            models.Index(
                fields=["facility", "status", "risk_level"],
                name="idx_event_facility_status_risk",
            ),
            # 최신 이벤트 정렬 (대시보드 "이벤트 현황" 패널)
            models.Index(
                fields=["facility", "-created_at"], name="idx_event_facility_time"
            ),
            # 발생원별 활성 이벤트 조회 (병합 로직)
            models.Index(
                fields=["source_sensor", "status"],
                name="idx_event_source_sensor_status",
                condition=models.Q(source_sensor__isnull=False),
            ),
        ]

    @property
    def is_mergeable_time_window(self) -> bool:
        """
        이벤트가 무한히 길어지는 것을 방지하기 위한 타임 윈도우 체크
        예: 최초 감지 후 12시간이 지났다면 더 이상 병합하지 않음
        """
        from datetime import timedelta
        from django.utils import timezone

        if not self.first_detected_at:
            return True

        # settings.py에 EVENT_MAX_MERGE_HOURS = 12 로 정의했다고 가정
        # max_hours = getattr(settings, 'EVENT_MAX_MERGE_HOURS', 12) max_duration = timedelta(hours=max_hours)
        max_duration = timedelta(hours=12)  # 도메인 요구사항에 맞게 조정
        return (timezone.now() - self.first_detected_at) <= max_duration
