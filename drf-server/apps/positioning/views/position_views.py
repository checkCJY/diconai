# apps/positioning/views/position_views.py
import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from apps.core.authentication import ServiceTokenAuthentication
from apps.positioning.serializers import WorkerPositionReceiveSerializer
from apps.positioning.services.position_service import handle_position_receive

logger = logging.getLogger(__name__)


class WorkerPositionReceiveView(APIView):
    """
    FastAPI로부터 작업자 위치 데이터 수신

    POST /api/positioning/receive/
    Body: [
        {
            "worker_id": 1,
            "facility_id": 1,
            "x": 150.0,
            "y": 120.0,
            "movement_status": "moving",
            "measured_at": "2026-04-21T10:00:00Z"
        },
        ...
    ]

    서버-서버(fastapi → drf) 호출 전용 ingest 엔드포인트.
    settings.INTERNAL_SERVICE_TOKEN 설정 시 Bearer 토큰 검증 (Phase 5),
    미설정 시 기존 무인증 동작 유지 (옵트인).
    """

    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Positioning (Ingest)"],
        summary="작업자 위치 배열 인입 (FastAPI → DRF)",
        description=(
            "FastAPI(:8001)가 IoT 위치 센서/더미로부터 받은 작업자 좌표 배열을 DRF에 영속화. "
            "배열 형태이며 단건당 worker_id/facility_id/x/y/movement_status/measured_at."
        ),
        request=WorkerPositionReceiveSerializer(many=True),
        responses={
            201: inline_serializer(
                name="PositionReceiveResponse",
                fields={
                    "saved": serializers.IntegerField(help_text="저장된 행 수"),
                    "ids": serializers.ListField(child=serializers.IntegerField()),
                    "statuses": serializers.ListField(
                        child=inline_serializer(
                            name="WorkerPositionStatus",
                            fields={
                                "worker_id": serializers.IntegerField(),
                                "risk_level": serializers.ChoiceField(
                                    choices=["normal", "warning", "danger"]
                                ),
                                "zone_name": serializers.CharField(allow_null=True),
                            },
                        ),
                        help_text=(
                            "작업자별 실시간 위험도(센서 측정값 기반) 및 "
                            "현재 진입한 지오펜스명. 프론트가 화면 표시에 사용."
                        ),
                    ),
                },
            ),
            400: OpenApiResponse(description="검증 실패 또는 배열이 아님"),
        },
    )
    def post(self, request):
        # 배열 형태로 받음
        if not isinstance(request.data, list):
            return Response(
                {"detail": "배열 형태로 전송해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = WorkerPositionReceiveSerializer(data=request.data, many=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        saved_ids = []
        statuses = []
        for item in serializer.validated_data:
            try:
                result = handle_position_receive(
                    worker_id=item["worker_id"],
                    facility_id=item["facility_id"],
                    x=item["x"],
                    y=item["y"],
                    movement_status=item.get("movement_status", "moving"),
                    measured_at=item["measured_at"],
                    node_id=item.get("node_id") or None,
                )
                statuses.append(
                    {
                        "worker_id": result["worker_id"],
                        "risk_level": result["risk_level"],
                        "zone_name": result["zone_name"],
                    }
                )
                if result["position_id"] is not None:
                    saved_ids.append(result["position_id"])
            except Exception:
                logger.exception("[positioning] 저장 오류 (item ignored)")

        return Response(
            {
                "saved": len(saved_ids),
                "ids": saved_ids,
                "statuses": statuses,
            },
            status=status.HTTP_201_CREATED,
        )
