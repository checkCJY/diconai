from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.operations.serializers import IntegrationLogCreateSerializer

# alarm_router(fastapi)와 대칭 패턴 — localhost-only IP 화이트리스트
_LOCAL_IPS = {"127.0.0.1", "::1", "localhost"}


class IntegrationLogInternalCreateView(APIView):
    """
    POST /api/internal/integration-logs/  — FastAPI → DRF IntegrationLog 기록

    [보안]
    localhost(127.0.0.1/::1)에서만 호출 가능. 외부 IP 시 403.
    JWT 인증 우회 (internal-only) — permission_classes = [AllowAny].

    [부하 정책]
    fire-and-forget 권장 (호출 측에서 raise_on_error=False로 본 흐름 비차단).
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # JWT 우회

    def post(self, request):
        client_ip = request.META.get("REMOTE_ADDR", "")
        if client_ip not in _LOCAL_IPS:
            return Response(
                {"detail": "내부 전용 엔드포인트입니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = IntegrationLogCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        log = serializer.save()
        return Response(
            {"id": log.id, "created_at": log.created_at},
            status=status.HTTP_201_CREATED,
        )
