# apps/accounts/views/internal_views.py
# 이성현 추가 — 내부 서비스(FastAPI)용 worker 목록 조회 API

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.authentication import ServiceTokenAuthentication
from apps.core.constants import UserType

User = get_user_model()


class InternalWorkerListView(APIView):
    """
    GET /api/internal/workers/  — FastAPI → DRF worker 목록 조회

    [보안]
    INTERNAL_SERVICE_TOKEN 헤더 검증. IP 화이트리스트 대신 토큰 인증 사용.
    Docker 네트워크 환경에서 FastAPI 컨테이너 IP가 달라도 정상 작동.

    [응답]
    [{"id": 3, "username": "worker_a"}, ...]
    user_type=worker 인 유저만 반환.
    """

    # 이성현 추가 — IP 화이트리스트 대신 ServiceTokenAuthentication 사용
    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Internal"],
        summary="worker 목록 조회 (FastAPI → DRF)",
        responses=inline_serializer(
            name="InternalWorkerListResponse",
            fields={
                "id": serializers.IntegerField(),
                "username": serializers.CharField(),
            },
            many=True,
        ),
    )
    def get(self, request):
        # worker 타입 유저만 id, username 반환
        workers = User.objects.filter(user_type=UserType.WORKER).values(
            "id", "username"
        )
        return Response(list(workers))
