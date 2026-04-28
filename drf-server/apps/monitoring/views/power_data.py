# monitoring/views/power_data.py
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.constants import POWER_THRESHOLDS
from apps.monitoring.serializers.power_data import (
    PowerDataBulkIngestSerializer,
    PowerEventIngestSerializer,
)


class PowerThresholdView(APIView):
    """
    GET /monitoring/api/power/thresholds/

    전력 임계치(W)를 반환한다. 프론트엔드 차트 주석 라인 및 위험도 판정에 사용.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(POWER_THRESHOLDS)


class PowerEventIngestView(APIView):
    """
    POST /monitoring/api/power/event/

    FastAPI로부터 ON/OFF 스냅샷(PowerEvent) 수신.
    요청 바디: { device_id, measured_at, snapshot }
    응답: { "id": <PowerEvent.id> }
    """

    permission_classes = [AllowAny]

    def post(self, request):
        s = PowerEventIngestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        event = s.save()
        return Response({"id": event.id}, status=status.HTTP_201_CREATED)


class PowerDataBulkIngestView(APIView):
    """
    POST /monitoring/api/power/data/

    FastAPI로부터 전류/전압/전력 16채널 데이터(PowerData) 일괄 수신.
    요청 바디: { device_id, measured_at, data_type, channels: [...] }
    응답: { "created": <저장된 행 수> }
    """

    permission_classes = [AllowAny]

    def post(self, request):
        s = PowerDataBulkIngestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rows = s.save()
        return Response({"created": len(rows)}, status=status.HTTP_201_CREATED)
