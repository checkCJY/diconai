# Create your models here.
from django.db import models


class AlarmRecord(models.Model):
    """
    알람 이력 — 위험 이벤트 발생 기록
    중복 방지: (sensor, gas_type, is_active=True) 조합 존재 시 신규 생성 스킵
    measured_value + threshold_value → 4차 AI 학습 데이터 활용
    """

    class AlarmType(models.TextChoices):
        GAS_THRESHOLD   = 'gas_threshold',   '가스 임계치 초과'
        POWER_OVERLOAD  = 'power_overload',  '전력 과부하'
        SENSOR_FAULT    = 'sensor_fault',    '센서 오류'

    class AlarmLevel(models.TextChoices):
        WARNING = 'warning', '주의'
        DANGER  = 'danger',  '위험'

    class Status(models.TextChoices):
        ACTIVE       = 'active',       '활성'
        ACKNOWLEDGED = 'acknowledged', '확인됨'
        RESOLVED     = 'resolved',     '해결됨'

    facility        = models.ForeignKey(
        'sensors.Facility',
        on_delete=models.CASCADE,
        related_name='alarm_records'
    )
    sensor          = models.ForeignKey(
        'sensors.GasSensor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alarm_records'
    )
    geofence        = models.ForeignKey(
        'geofence.GeoFence',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alarm_records'
    )
    worker          = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alarm_records'
    )
    resolved_by     = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_alarms'
    )
    alarm_type      = models.CharField(
        max_length=100,
        choices=AlarmType.choices
    )
    gas_type        = models.CharField(max_length=10, null=True, blank=True)
    measured_value  = models.FloatField(null=True, blank=True)
    threshold_value = models.FloatField(null=True, blank=True)
    alarm_level     = models.CharField(
        max_length=10,
        choices=AlarmLevel.choices
    )
    is_active       = models.BooleanField(default=True)
    status          = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    resolved_at     = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.alarm_level}] {self.alarm_type} - {self.created_at}"

    class Meta:
        db_table = 'alarm_record'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['is_active', 'alarm_level'],
                name='idx_alarm_record_active_level'
            )
        ]


class Notification(models.Model):
    """
    알림 — 알람 발생 시 사용자에게 실제 발송
    is_broadcast=True면 공장 전체 발송, target_user는 NULL
    알람 1개에서 여러 알림 생성 가능
    """

    class Severity(models.TextChoices):
        NORMAL  = 'normal',  '정상'
        WARNING = 'warning', '주의'
        DANGER  = 'danger',  '위험'

    alarm           = models.ForeignKey(
        AlarmRecord,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    target_user     = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    is_broadcast    = models.BooleanField(default=False)
    title           = models.CharField(max_length=100)
    content         = models.TextField()
    severity        = models.CharField(
        max_length=10,
        choices=Severity.choices,
        default=Severity.NORMAL
    )
    is_read         = models.BooleanField(default=False)
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.created_at}"

    class Meta:
        db_table = 'notification'
        ordering = ['-created_at']


class SafetyCheckItem(models.Model):
    """
    안전 체크리스트 항목 — 관리자가 등록
    공장별 독립적인 체크리스트 구성 가능
    order로 표시 순서 지정, 공장 내 순서 중복 불가
    """

    facility    = models.ForeignKey(
        'sensors.Facility',
        on_delete=models.CASCADE,
        related_name='safety_check_items'
    )
    title       = models.CharField(max_length=100)
    is_required = models.BooleanField(default=True)
    order       = models.IntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.facility.name} - {self.title}"

    class Meta:
        db_table = 'safety_check_item'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(
                fields=['facility', 'order'],
                name='uq_safety_check_item_facility_order'
            )
        ]


class SafetyStatus(models.Model):
    """
    작업자 체크 결과 — 항목별 체크 시각과 완료 여부 저장
    checked_at은 is_checked=True일 때만 유효
    """

    worker      = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.CASCADE,
        related_name='safety_statuses'
    )
    check_item  = models.ForeignKey(
        SafetyCheckItem,
        on_delete=models.CASCADE,
        related_name='safety_statuses'
    )
    is_checked  = models.BooleanField(default=False)
    checked_at  = models.DateTimeField(null=True, blank=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        status = '완료' if self.is_checked else '미완료'
        return f"{self.worker.username} - {self.check_item.title} ({status})"

    class Meta:
        db_table = 'safety_status'
        ordering = ['check_item__order']
        constraints = [
            models.UniqueConstraint(
                fields=['worker', 'check_item'],
                name='uq_safety_status_worker_item'
            )
        ]


class SystemLog(models.Model):
    """
    시스템 로그 — 모든 중요한 변경 사항 기록
    ISO45001 감사 대응 + 장애 추적 목적
    actor NULL 허용 — 탈퇴 사용자 과거 로그 보존
    """

    class ActionType(models.TextChoices):
        THRESHOLD_UPDATE  = 'threshold_update',  '임계치 수정'
        GEOFENCE_CREATE   = 'geofence_create',   '위험구역 생성'
        GEOFENCE_UPDATE   = 'geofence_update',   '위험구역 수정'
        GEOFENCE_DELETE   = 'geofence_delete',   '위험구역 삭제'
        ALARM_RESOLVE     = 'alarm_resolve',     '알람 해제'
        SENSOR_REGISTER   = 'sensor_register',   '센서 등록'
        USER_CREATE       = 'user_create',       '사용자 생성'
        USER_UPDATE       = 'user_update',       '사용자 수정'

    actor        = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_logs'
    )
    action_type  = models.CharField(
        max_length=50,
        choices=ActionType.choices
    )
    target_model = models.CharField(max_length=100, null=True, blank=True)
    target_id    = models.IntegerField(null=True, blank=True)
    old_value    = models.JSONField(null=True, blank=True)
    new_value    = models.JSONField(null=True, blank=True)
    ip_address   = models.CharField(max_length=100, null=True, blank=True)
    timestamp    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action_type} - {self.timestamp}"

    class Meta:
        db_table = 'system_log'
        ordering = ['-timestamp']