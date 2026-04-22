from rest_framework import serializers

from apps.facilities.models import GasSensor
from apps.monitoring.models.gas_data import GasData


class GasDataCreateSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(write_only=True)

    class Meta:
        model = GasData
        fields = [
            "device_id",
            "measured_at",
            # 가스 측정값 9종 (lel 제외 — 모델 컬럼 없음, raw_payload에 보관)
            "co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc",
            # 가스별 위험도 9종
            "co_risk", "h2s_risk", "co2_risk", "o2_risk", "no2_risk",
            "so2_risk", "o3_risk", "nh3_risk", "voc_risk",
            # 원본 페이로드 (lel 포함 전체)
            "raw_payload",
        ]

    def validate(self, attrs):
        device_id = attrs.pop("device_id")
        try:
            attrs["gas_sensor"] = GasSensor.objects.get(
                device_id=device_id, is_active=True
            )
        except GasSensor.DoesNotExist:
            raise serializers.ValidationError(
                {"device_id": f"등록되지 않은 장치입니다: {device_id}"}
            )
        return attrs

    def create(self, validated_data):
        gas_data = GasData.objects.create(**validated_data)
        # 마지막 수신 시각 갱신
        gas_data.gas_sensor.last_reading = gas_data.measured_at
        gas_data.gas_sensor.save(update_fields=["last_reading", "updated_at"])
        return gas_data
