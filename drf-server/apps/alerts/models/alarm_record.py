# alerts/models/alarm_record.py
from django.conf import settings
from django.db import models

from apps.core.constants import AlarmType, GasTypeChoices, RiskLevel
from apps.core.models.base import BaseModel


class AlarmRecord(BaseModel):
    """
    센서 자동 판정 결과 — 원자적 불변 기록

    [v4 재설계 — 역할 축소]
    v2의 is_active, status, resolved_by, resolved_at 필드 전부 제거
    이들은 업무 상태이므로 Event가 관리
    AlarmRecord는 판정의 순간적 사실만 기록 (불변)

    [발생원 FK 정책]
    alarm_type별로 사용하는 FK가 다름:
    - GAS_THRESHOLD      → sensor (GasSensor)
    - POWER_OVERLOAD     → power_device (PowerDevice)
    - GEOFENCE_INTRUSION → geofence + worker
    - SENSOR_FAULT       → sensor 또는 power_device
    사용하지 않는 FK는 NULL

    [Event 연결]
    event FK는 null 허용
    - AlarmRecord 생성 직후 Event에 묶임 (정상 플로우)
    - 묶임 전 상태(단기간) 또는 독립 알람도 허용

    [불변성 보장]
    save() 오버라이드로 수정 차단 — 생성만 허용
    """

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, related_name="alarm_records"
    )
    event = models.ForeignKey(
        "alerts.Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alarms",
        verbose_name="묶인 이벤트",
    )

    # 발생원 FK (alarm_type별로 선택적 사용)
    sensor = models.ForeignKey(
        "facilities.GasSensor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alarm_records",
    )
    power_device = models.ForeignKey(
        "facilities.PowerDevice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alarm_records",
    )
    geofence = models.ForeignKey(
        "geofence.GeoFence",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alarm_records",
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alarm_records_as_worker",
    )

    # ML 추론 메타 (POWER_ANOMALY_AI 등 AI 알람 시 MLAnomalyResult 와 PK join 용)
    # nullable: 임계치 알람·기존 데이터는 None 유지
    ml_anomaly_result = models.ForeignKey(
        "ml.MLAnomalyResult",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alarm_records",
        db_index=True,
    )

    # 판정 내용
    alarm_type = models.CharField(
        max_length=30, choices=AlarmType.choices, verbose_name="알람 유형"
    )
    gas_type = models.CharField(
        max_length=10,
        choices=GasTypeChoices.choices,
        blank=True,
        default="",
        verbose_name="가스 종류 (GAS_THRESHOLD 시)",
    )
    measured_value = models.FloatField(null=True, blank=True, verbose_name="측정값")
    threshold_value = models.FloatField(
        null=True, blank=True, verbose_name="초과 임계치"
    )
    risk_level = models.CharField(
        max_length=10, choices=RiskLevel.choices, verbose_name="위험도"
    )
    # created_at / updated_at / updated_by 는 BaseModel 상속 (save override로 수정 차단)

    def save(self, *args, **kwargs):
        """생성만 허용 — 수정 차단"""
        if self.pk is not None:
            # event FK (병합 시) + ml_anomaly_result FK (AI 알람 ML 메타 연결 시) 만 예외 허용
            update_fields = kwargs.get("update_fields")
            allowed = {"event", "ml_anomaly_result"}
            if update_fields is None or not set(update_fields).issubset(allowed):
                raise ValueError(
                    "AlarmRecord는 수정할 수 없습니다. "
                    "event / ml_anomaly_result 필드만 사후 연결 시 업데이트 가능합니다."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AlarmRecord는 삭제할 수 없습니다.")

    class Meta:
        db_table = "alarm_record"
        indexes = [
            models.Index(fields=["event", "-created_at"], name="idx_alarm_event_time"),
            models.Index(
                fields=["sensor", "-created_at"], name="idx_alarm_sensor_time"
            ),
            models.Index(
                fields=["facility", "alarm_type", "-created_at"],
                name="idx_alarm_facility_type_time",
            ),
        ]
