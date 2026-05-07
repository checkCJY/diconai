# monitoring/views/power_data.py
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
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
    공개 데이터(상수)이므로 인증 불필요.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Monitoring (Public)"],
        summary="전력 임계치(W) 조회",
        description="채널별 주의/위험 임계치(W). 프론트 차트 주석 라인 및 위험도 판정에 사용.",
        responses={
            200: inline_serializer(
                name="PowerThresholds",
                fields={
                    "warning": serializers.FloatField(help_text="주의 임계치 (W)"),
                    "danger": serializers.FloatField(help_text="위험 임계치 (W)"),
                },
            )
        },
    )
    def get(self, request):
        return Response(POWER_THRESHOLDS)


class PowerEventIngestView(APIView):
    """
    POST /monitoring/api/power/event/

    FastAPI로부터 ON/OFF 스냅샷(PowerEvent) 수신.
    요청 바디: { device_id, measured_at, snapshot }
    응답: { "id": <PowerEvent.id> }

    의도적 무인증: 서버-서버(fastapi → drf) 호출 전용 ingest 엔드포인트.
    Phase 5에서 서비스 토큰 또는 IP 화이트리스트 기반 보호 추가 예정.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Monitoring (Ingest)"],
        summary="전력 ON/OFF 스냅샷 인입 (FastAPI → DRF)",
        description="FastAPI(:8001)가 16채널 ON/OFF 변화 스냅샷을 PowerEvent로 영속화. 무인증 서버-서버 전용.",
        request=PowerEventIngestSerializer,
        responses={
            201: inline_serializer(
                name="PowerEventIngestResponse",
                fields={"id": serializers.IntegerField()},
            ),
            400: OpenApiResponse(description="검증 실패"),
        },
    )
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

    의도적 무인증: 서버-서버(fastapi → drf) 호출 전용 ingest 엔드포인트.
    Phase 5에서 서비스 토큰 또는 IP 화이트리스트 기반 보호 추가 예정.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Monitoring (Ingest)"],
        summary="전력 16채널 측정값 일괄 인입 (FastAPI → DRF)",
        description=(
            "전류(A) / 전압(V) / 전력(W) 측정값 16채널을 한 번에 PowerData로 영속화. "
            "data_type 필드로 측정 종류 구분. 무인증 서버-서버 전용."
        ),
        request=PowerDataBulkIngestSerializer,
        responses={
            201: inline_serializer(
                name="PowerDataBulkIngestResponse",
                fields={"created": serializers.IntegerField(help_text="저장된 행 수")},
            ),
            400: OpenApiResponse(description="검증 실패"),
        },
        examples=[
            OpenApiExample(
                "전력(W) 측정값 16채널",
                description="data_type='watt'인 경우. 채널 -1 값은 통신 불능 채널(저장은 됨)",
                value={
                    "device_id": "power_01",
                    "measured_at": "2026-05-06T17:00:00Z",
                    "data_type": "watt",
                    "channels": [
                        {"channel": 1, "value": 1850},
                        {"channel": 2, "value": 1620},
                        {"channel": 3, "value": -1},
                        {"channel": 4, "value": 2100},
                    ],
                },
                request_only=True,
            ),
            OpenApiExample(
                "정상 응답",
                value={"created": 16},
                response_only=True,
                status_codes=["201"],
            ),
        ],
    )
    def post(self, request):
        s = PowerDataBulkIngestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rows = s.save()
        return Response({"created": len(rows)}, status=status.HTTP_201_CREATED)
