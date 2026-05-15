"""AI 이상탐지 알람 INSERT forward endpoint.

POST /alerts/api/anomaly-alarm-records/

호출자: fastapi `services.anomaly_alarm.forward_inference_e2e` (fire-and-forget).
내부: 기존 `create_alarm_and_event` 재사용 → Event 자동 병합·EventLog·AlertPolicy
매칭 그대로 흡수. ml_anomaly_result_id 가 있으면 생성된 AlarmRecord 에 사후 연결.

[현재 sprint 범위: 전력만]
alarm_type=power_anomaly_ai 만 처리. 가스 (gas_anomaly_ai) 는 enum 정의 후 가스
트랙 후속 sprint 에서 분기 활성화.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.serializers.anomaly_alarm_record import (
    AnomalyAlarmRecordPayloadSerializer,
)
from apps.alerts.services.event_service import create_alarm_and_event
from apps.core.constants import AlarmType
from apps.facilities.models import GasSensor, PowerDevice  # 가스 센서 추가

logger = logging.getLogger(__name__)


class AnomalyAlarmRecordCreateView(APIView):
    """AI 이상탐지 알람 INSERT. 내부 API — fastapi 만 호출."""

    # 내부 API. drf_client 가 부착하는 invalid Bearer 토큰을 JWTAuthentication 이
    # 401 처리하지 않도록 인증 자체 skip. (ml/views.py 의 ActiveMLModelView 와 동일 패턴)
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        serializer = AnomalyAlarmRecordPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        alarm_type = data["alarm_type"]
        source_kwargs = self._resolve_source(alarm_type, data)
        if source_kwargs is None:
            return Response(
                {"detail": "발생원 장비/센서를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        facility_id, fk_kwargs = source_kwargs

        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=alarm_type,
            risk_level=data["risk_level"],
            measured_value=data.get("measured_value"),
            gas_type=data.get("gas_type") or "",
            summary=data.get("summary", ""),
            source_label=data.get("source_label", ""),
            detected_at=data["detected_at"],
            **fk_kwargs,
        )

        # ml_anomaly_result FK 사후 연결 (alarm 생성된 경우만)
        ml_id = data.get("ml_anomaly_result_id")
        if alarm is not None and ml_id is not None:
            alarm.ml_anomaly_result_id = ml_id
            alarm.save(update_fields=["ml_anomaly_result"])

        return Response(
            {
                "alarm_id": alarm.id if alarm else None,
                "event_id": event.id if event else None,
            },
            status=status.HTTP_201_CREATED,
        )

    def _resolve_source(self, alarm_type: str, data: dict):
        """alarm_type 별 source FK lookup → (facility_id, kwargs) 또는 None."""
        if alarm_type == AlarmType.POWER_ANOMALY_AI:
            device_id_str = data.get("source_device_id")
            if not device_id_str:
                return None
            try:
                device = PowerDevice.objects.get(device_id=device_id_str)
            except PowerDevice.DoesNotExist:
                logger.warning(
                    "[anomaly_alarm_forward] PowerDevice not found device_id=%s",
                    device_id_str,
                )
                return None
            return device.facility_id, {"power_device_id": device.id}

        # 이성현 추가 — 가스 AI 알람 분기 활성화
        elif alarm_type == AlarmType.GAS_ANOMALY_AI:
            sensor_id_str = data.get("source_sensor_id")
            if not sensor_id_str:
                return None
            try:
                sensor = GasSensor.objects.get(device_id=sensor_id_str)
            except GasSensor.DoesNotExist:
                logger.warning(
                    "[anomaly_alarm_forward] GasSensor not found device_id=%s",
                    sensor_id_str,
                )
                return None
            return sensor.facility_id, {"sensor_id": sensor.id}

        return None
