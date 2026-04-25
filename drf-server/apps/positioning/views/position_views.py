# apps/positioning/views/position_views.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from apps.positioning.serializers import WorkerPositionReceiveSerializer
from apps.positioning.services.position_service import handle_position_receive


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
    """

    permission_classes = [AllowAny]  # FastAPI 내부 통신이므로 인증 생략

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

        saved = []
        for item in serializer.validated_data:
            try:
                pos = handle_position_receive(
                    worker_id=item["worker_id"],
                    facility_id=item["facility_id"],
                    x=item["x"],
                    y=item["y"],
                    movement_status=item.get("movement_status", "moving"),
                    measured_at=item["measured_at"],
                )
                if pos is not None:
                    saved.append(pos.id)
            except Exception as e:
                print(f"[positioning] 저장 오류: {e}")

        return Response(
            {"saved": len(saved), "ids": saved}, status=status.HTTP_201_CREATED
        )
