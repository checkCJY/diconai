from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.monitoring.serializers import GasDataCreateSerializer


class GasDataCreateView(APIView):
    """
    POST /api/monitoring/gas/
    FastAPI로부터 가스 측정값을 수신하여 DB에 저장하고 알람을 생성한다.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = GasDataCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gas_data = serializer.save()
        alarms = getattr(gas_data, "_alarms", [])
        return Response(
            {"id": gas_data.id, "received": True, "alarms": alarms},
            status=status.HTTP_201_CREATED,
        )
