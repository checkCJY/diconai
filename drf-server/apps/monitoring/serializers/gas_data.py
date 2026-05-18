import time

from django.db import IntegrityError, OperationalError

from rest_framework import serializers

from apps.core.metrics import DB_SAVE_DURATION, DB_SAVE_TOTAL
from apps.facilities.models import GasSensor
from apps.monitoring.models.gas_data import GasData


class GasDataCreateSerializer(serializers.ModelSerializer):
    """
    FastAPI → DRF: GasData 수신 시리얼라이저.

    필드:
      device_id              : GasSensor.device_id → FK 매핑
      measured_at            : 장치 측정 시각 (UTC ISO 문자열)
      9종 가스 측정값         : co/h2s/co2/o2/no2/so2/o3/nh3/voc
      9종 위험도              : *_risk (FastAPI 가 임계치 기준으로 계산)
      raw_payload            : 원본(lel 포함)
      is_anomaly/anomaly_type: 더미 시뮬레이터 시나리오 라벨 (IF 학습 평가용).
                               운영 센서 페이로드는 비워서 기본값(False/None) 저장.
    """

    device_id = serializers.CharField(write_only=True)
    ingress_ts = serializers.FloatField(required=False, allow_null=True, default=None, write_only=True)

    class Meta:
        model = GasData
        fields = [
            "device_id",
            "ingress_ts",
            "measured_at",
            # 가스 측정값 9종 (lel 제외 — 모델 컬럼 없음, raw_payload에 보관)
            "co",
            "h2s",
            "co2",
            "o2",
            "no2",
            "so2",
            "o3",
            "nh3",
            "voc",
            # 가스별 위험도 9종
            "co_risk",
            "h2s_risk",
            "co2_risk",
            "o2_risk",
            "no2_risk",
            "so2_risk",
            "o3_risk",
            "nh3_risk",
            "voc_risk",
            # 원본 페이로드 (lel 포함 전체)
            "raw_payload",
            # IF 학습 라벨 (시뮬레이터 전용, 운영은 빈 값)
            "is_anomaly",
            "anomaly_type",
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
        ingress_ts = validated_data.pop("ingress_ts", None)
        # DB_SAVE_TOTAL: GasData 저장 성공/실패를 추적한다.
        # SQLite 운영 중 동시 쓰기 증가 시 "database is locked" OperationalError가 발생.
        # 이 에러 빈도를 모니터링해 PostgreSQL 마이그레이션 타이밍을 결정하는 데 사용한다.
        _t = time.perf_counter()
        try:
            gas_data = GasData.objects.create(**validated_data)
        except OperationalError as e:
            error_type = "db_locked" if "database is locked" in str(e).lower() else "other"
            DB_SAVE_TOTAL.labels(model="gas", result="error", error_type=error_type).inc()
            raise
        except IntegrityError:
            DB_SAVE_TOTAL.labels(model="gas", result="error", error_type="integrity").inc()
            raise
        except Exception:
            DB_SAVE_TOTAL.labels(model="gas", result="error", error_type="other").inc()
            raise
        finally:
            DB_SAVE_DURATION.labels(model="gas").observe(time.perf_counter() - _t)

        DB_SAVE_TOTAL.labels(model="gas", result="ok", error_type="").inc()

        gas_data.gas_sensor.last_reading = gas_data.measured_at
        gas_data.gas_sensor.save(update_fields=["last_reading", "updated_at"])

        from apps.monitoring.services.gas_alarm import trigger_gas_alarms

        gas_data._alarms = trigger_gas_alarms(gas_data, ingress_ts=ingress_ts)

        return gas_data
