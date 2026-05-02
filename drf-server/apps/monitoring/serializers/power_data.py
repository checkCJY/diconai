# monitoring/serializers/power_data.py
from rest_framework import serializers

from apps.core.constants import RiskLevel, SensorStatus
from apps.facilities.models.devices import PowerDevice
from apps.monitoring.models import PowerData, PowerEvent
from apps.monitoring.services.power_alarm import trigger_power_alarms


class PowerEventIngestSerializer(serializers.Serializer):
    """
    FastAPI → DRF: PowerEvent 수신 시리얼라이저 (ON/OFF 스냅샷)

    입력 필드:
      device_id   : PowerDevice.device_id (하드웨어 식별자)
      measured_at : 장치 측정 시각 — FastAPI가 UTC ISO 문자열로 주입
      snapshot    : {"1": bool, ..., "16": bool} — PowerOnOffPayload.to_snapshot() 결과

    처리:
      - device_id → PowerDevice FK 조회
      - 직전 스냅샷과 비교하여 changed_channels 자동 계산
        (최초 수신 시 None, 이후 변경된 채널 번호 리스트)
    """

    device_id = serializers.CharField(max_length=50)
    measured_at = serializers.DateTimeField()
    snapshot = serializers.DictField(child=serializers.BooleanField())

    def validate_snapshot(self, value):
        try:
            PowerEvent.validate_snapshot(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))
        return value

    def create(self, validated_data):
        device = PowerDevice.objects.get(device_id=validated_data["device_id"])

        last_event = (
            PowerEvent.objects.filter(power_device=device)
            .order_by("-created_at")
            .first()
        )
        if last_event is None:
            changed_channels = None
        else:
            snapshot = validated_data["snapshot"]
            changed_channels = [
                int(k) for k in snapshot if snapshot[k] != last_event.snapshot.get(k)
            ]

        return PowerEvent.objects.create(
            power_device=device,
            snapshot=validated_data["snapshot"],
            changed_channels=changed_channels,
            measured_at=validated_data["measured_at"],
        )


class _ChannelEntrySerializer(serializers.Serializer):
    """PowerDataBulkIngestSerializer 내부용 채널 단건 시리얼라이저."""

    channel = serializers.IntegerField(min_value=1, max_value=16)
    value = serializers.FloatField(allow_null=True, required=False, default=None)
    sensor_status = serializers.ChoiceField(
        choices=SensorStatus.choices,
        default=SensorStatus.ACTIVE,
    )
    risk_level = serializers.ChoiceField(
        choices=RiskLevel.choices,
        default=RiskLevel.NORMAL,
    )


class PowerDataBulkIngestSerializer(serializers.Serializer):
    """
    FastAPI → DRF: PowerData 16채널 일괄 수신 시리얼라이저 (전류/전압/전력)

    입력 필드:
      device_id   : PowerDevice.device_id
      measured_at : 장치 측정 시각 — FastAPI가 UTC ISO 문자열로 주입
      data_type   : "current" | "voltage" | "watt"
      channels    : [{channel: int, value: float, risk_level: str}, ...]
                    — PowerMeasurementPayload.to_channel_values() 변환 후 전달

    처리:
      - device_id → PowerDevice FK 조회
      - 16채널 PowerData 일괄 생성 (bulk_create, uq 충돌 시 무시)
      - 통신 불능 채널: value=None, sensor_status='comm_failure'로 저장
    """

    device_id = serializers.CharField(max_length=50)
    measured_at = serializers.DateTimeField()
    data_type = serializers.ChoiceField(choices=PowerData.DataType.choices)
    channels = _ChannelEntrySerializer(many=True)

    def create(self, validated_data):
        device = PowerDevice.objects.get(device_id=validated_data["device_id"])
        objs = [
            PowerData(
                power_device=device,
                channel=ch["channel"],
                data_type=validated_data["data_type"],
                value=ch["value"],
                sensor_status=ch["sensor_status"],
                risk_level=ch["risk_level"],
                measured_at=validated_data["measured_at"],
            )
            for ch in validated_data["channels"]
        ]
        PowerData.objects.bulk_create(objs, ignore_conflicts=True)
        trigger_power_alarms(
            objs, device
        )  # watt 채널에 대해 위험도 판정 후 알람 라우팅
        return objs
