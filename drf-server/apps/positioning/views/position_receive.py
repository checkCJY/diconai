from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.positioning.services.position_service import handle_position_receive


class PositionReceiveView(APIView):
    """
    POST /positioning/api/receive/
    FastAPI 서버 또는 IoT 디바이스에서 작업자 위치 데이터 수신.
    위치 저장 → 지오펜스 판정 → 위험구역 진입 시 알람 생성.

    요청 바디:
    {
        "worker_id": int,
        "facility_id": int,
        "x": float,
        "y": float,
        "measured_at": "2024-01-01T00:00:00Z"
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        required = ["worker_id", "facility_id", "x", "y", "measured_at"]
        missing = [f for f in required if f not in data]
        if missing:
            return Response(
                {"status": "error", "message": f"필수 필드 누락: {missing}"},
                status=400,
            )

        measured_at = parse_datetime(data["measured_at"])
        if measured_at is None:
            return Response(
                {"status": "error", "message": "measured_at 형식 오류 (ISO8601 필요)"},
                status=400,
            )
        if timezone.is_naive(measured_at):
            measured_at = timezone.make_aware(measured_at)

        try:
            pos = handle_position_receive(
                worker_id=int(data["worker_id"]),
                facility_id=int(data["facility_id"]),
                x=float(data["x"]),
                y=float(data["y"]),
                measured_at=measured_at,
            )
        except Exception as e:
            print(f"[PositionReceiveView] 처리 실패: {e}")
            return Response({"status": "error", "message": str(e)}, status=500)

        print(
            f"[PositionReceiveView] 위치 수신 완료: worker={data['worker_id']} pos_id={pos.id} geofence={pos.current_geofence_id}"
        )
        return Response({"status": "success", "position_id": pos.id}, status=201)
