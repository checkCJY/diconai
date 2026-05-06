from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.monitoring.serializers import GasDataCreateSerializer


class GasDataCreateView(APIView):
    """
    POST /api/monitoring/gas/
    FastAPI로부터 가스 측정값을 수신하여 DB에 저장하고 알람을 생성한다.

    의도적 무인증: 서버-서버(fastapi → drf) 호출 전용 ingest 엔드포인트.
    Phase 5에서 fastapi 측 서비스 토큰 또는 IP 화이트리스트 기반 보호 추가 예정.
    """

    authentication_classes = []
    permission_classes = []

    @extend_schema(
        tags=["Monitoring (Ingest)"],
        summary="가스 측정값 인입 (FastAPI → DRF)",
        description=(
            "FastAPI(:8001)가 IoT 가스 센서로부터 받은 측정값을 DRF에 영속화 요청.\n\n"
            "**무인증** — 서버-서버 호출 전용. 외부 노출 금지(이상적으로 reverse proxy에서 차단). "
            "Phase 5+에서 `DRF_SERVICE_TOKEN` 또는 IP 화이트리스트로 보호 예정."
        ),
        request=GasDataCreateSerializer,
        responses={
            201: inline_serializer(
                name="GasDataIngestResponse",
                fields={
                    "id": serializers.IntegerField(help_text="GasData.id"),
                    "received": serializers.BooleanField(),
                    "alarms": serializers.ListField(child=serializers.DictField()),
                },
            ),
            400: OpenApiResponse(description="검증 실패"),
        },
        examples=[
            OpenApiExample(
                "정상 가스 측정 페이로드",
                description="FastAPI에서 1초 주기로 전송하는 9종 가스 측정값",
                value={
                    "device_id": "sensor_01",
                    "received_at": "2026-05-06T17:00:00Z",
                    "co": 5.2,
                    "h2s": 0.5,
                    "co2": 800,
                    "o2": 20.9,
                    "no2": 0.1,
                    "so2": 0.05,
                    "o3": 0.02,
                    "nh3": 1.0,
                    "voc": 0.5,
                    "max_risk_level": "normal",
                },
                request_only=True,
            ),
            OpenApiExample(
                "정상 응답",
                value={"id": 12345, "received": True, "alarms": []},
                response_only=True,
                status_codes=["201"],
            ),
            OpenApiExample(
                "위험 가스 감지 응답 (알람 동반)",
                value={
                    "id": 12346,
                    "received": True,
                    "alarms": [
                        {
                            "gas_type": "co",
                            "risk_level": "danger",
                            "measured_value": 250,
                            "threshold": 200,
                        },
                    ],
                },
                response_only=True,
                status_codes=["201"],
            ),
        ],
    )
    def post(self, request):
        serializer = GasDataCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gas_data = serializer.save()
        alarms = getattr(gas_data, "_alarms", [])
        return Response(
            {"id": gas_data.id, "received": True, "alarms": alarms},
            status=status.HTTP_201_CREATED,
        )
