# apps/operations/views/internal/integration_log.py
# 이성현 수정 — IP 화이트리스트 → ServiceTokenAuthentication 으로 교체
# Docker 환경에서 FastAPI 컨테이너 IP가 172.18.x.x 라 127.0.0.1 화이트리스트가 항상 403

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.authentication import ServiceTokenAuthentication
from apps.operations.serializers import IntegrationLogCreateSerializer


class IntegrationLogInternalCreateView(APIView):
    """
    POST /api/internal/integration-logs/  — FastAPI → DRF IntegrationLog 기록

    [보안]
    INTERNAL_SERVICE_TOKEN 헤더 검증. IP 화이트리스트 대신 토큰 인증 사용.
    Docker 네트워크 환경에서 FastAPI 컨테이너 IP가 달라도 정상 작동.

    [부하 정책]
    fire-and-forget 권장 (호출 측에서 raise_on_error=False로 본 흐름 비차단).
    """

    # 이성현 수정 — ServiceTokenAuthentication 으로 교체
    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Internal"],
        summary="IntegrationLog 기록 (FastAPI → DRF)",
        request=IntegrationLogCreateSerializer,
        responses=inline_serializer(
            name="IntegrationLogCreateResponse",
            fields={
                "id": serializers.IntegerField(),
                "created_at": serializers.DateTimeField(),
            },
        ),
    )
    def post(self, request):
        serializer = IntegrationLogCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        log = serializer.save()
        return Response(
            {"id": log.id, "created_at": log.created_at},
            status=status.HTTP_201_CREATED,
        )
