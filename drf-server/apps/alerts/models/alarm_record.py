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
    # PowerDevice 알람 시 채널 (1~16). PowerDevice 1대 안 16개 측정점 (송풍기/압연기 등)
    # 중 어느 채널이 알람인지 추적. get_short_message 가 channel + power_device.channel_meta
    # 로 운영자 친화 라벨 ("송풍기A 임계치 초과 (15.58 W)") 생성. 가스/지오펜스는 NULL.
    channel = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="PowerDevice 채널 (1~16)"
    )
    measured_value = models.FloatField(null=True, blank=True, verbose_name="측정값")
    threshold_value = models.FloatField(
        null=True, blank=True, verbose_name="초과 임계치"
    )
    risk_level = models.CharField(
        max_length=10, choices=RiskLevel.choices, verbose_name="위험도"
    )
    # W4.a — AI 알람 한정 algorithm 출처 라벨 (ARIMA un-downgrade plan §8).
    # power/gas anomaly_ai 알람만 채워지고 룰 기반은 빈 문자열 또는 NULL.
    # 값: "isolation_forest" | "arima" | "combined" | "night_abnormal" | "" | NULL
    # Critical #1 (0018) — null=True 추가: Django SQLite ALTER TABLE ADD COLUMN 이
    # column DEFAULT 미적용하는 이슈 대비. ORM 흐름은 default="" 그대로, raw SQL /
    # 옛 ORM 캐시 INSERT 시 NULL 도 허용해 IntegrityError 방지. NULL/'' 둘 다
    # "AI 알람 아님" 의미로 동일 취급 (filter 시 isnull=True or exact="" 양쪽 고려).
    algorithm_source = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        default="",
        verbose_name="AI 알고리즘 출처",
        help_text=(
            "power/gas anomaly_ai 알람만 채움. isolation_forest / arima / "
            "combined / night_abnormal. 룰 알람은 빈 문자열 또는 NULL."
        ),
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

    def get_short_message(self) -> str:
        """이벤트 현황 패널·WS push payload 의 한 줄 message.

        운영자 안내문(summary, 긴 한글)과 구분되는 도메인 사실만 담은 짧은 텍스트.
        DRF AlarmRecordSerializer 와 Celery `_push_to_ws` 양쪽이 본 메서드를 호출
        → API 응답 / WS payload 가 항상 같은 텍스트를 노출 (drift 방지).
        """
        if self.gas_type and self.measured_value is not None:
            # AI 알람이면 algorithm 출처 라벨 prefix (예: "CO ARIMA 이상 감지")
            if self.alarm_type == "gas_anomaly_ai":
                from apps.core.constants import ALGORITHM_SOURCE_LABEL

                label = ALGORITHM_SOURCE_LABEL.get(self.algorithm_source or "", "AI")
                return (
                    f"{self.gas_type.upper()} {label} 이상 감지 "
                    f"({self.measured_value} ppm)"
                )
            return f"{self.gas_type.upper()} 임계치 초과 ({self.measured_value} ppm)"
        if self.power_device_id and self.measured_value is not None:
            # PowerDevice 1대 안 16채널 중 어느 측정점인지 운영자 친화 라벨 prefix.
            # channel_meta 에 등록된 이름("송풍기A") 우선, 없으면 "CH{N}". channel 자체가
            # NULL 인 옛 데이터는 prefix 생략 (post-channel-migration backfill 안 함).
            prefix = ""
            if self.channel is not None and self.power_device is not None:
                prefix = f"{self.power_device.get_channel_label(self.channel)} "
            if self.alarm_type == "power_anomaly_ai":
                # algorithm_source 라벨 표시 ("송풍기A IF+ARIMA 이상 감지 ...").
                # 빈값/NULL 또는 미매핑 코드는 "AI" fallback.
                from apps.core.constants import ALGORITHM_SOURCE_LABEL

                label = ALGORITHM_SOURCE_LABEL.get(self.algorithm_source or "", "AI")
                return f"{prefix}{label} 이상 감지 ({self.measured_value} W)"
            return f"{prefix}전력 임계치 초과 ({self.measured_value} W)"
        if self.geofence_id:
            return "위험구역 진입"
        if self.alarm_type == "sensor_fault":
            return "센서 통신 이상"
        if self.alarm_type in ("gas_clear", "power_clear"):
            return "정상 복귀"
        # 화면 정책 알람 (PPE, VR 교육 등) — choices 한글 라벨 사용.
        return self.get_alarm_type_display()

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
