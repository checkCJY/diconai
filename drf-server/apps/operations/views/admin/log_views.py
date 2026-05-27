"""
operations/views/admin/log_views.py

시스템 로그(AppLog)와 연동 로그(IntegrationLog) 관리자 조회 뷰.

흐름에서 이 파일의 위치:
  HTTP GET 요청 → urls.py 라우팅 → [이 파일] → Serializer → DB → 응답

왜 admin/ 폴더에 따로 두는가:
  operations/views/internal/ 은 FastAPI → DRF 내부 호출용 (JWT 우회, localhost only).
  operations/views/admin/    은 관리자 화면에서 호출하는 조회용 (JWT 인증 필요).
  같은 폴더에 두면 "이 뷰가 외부용인지 내부용인지" 코드를 열어봐야 알 수 있다.
  폴더로 구분하면 파일 이름만 봐도 용도가 명확하다.

두 뷰 모두 읽기 전용(GET만)인 이유:
  AppLog, IntegrationLog는 APPEND-ONLY 모델이다.
  모델 레벨에서 수정·삭제를 막고 있으므로 뷰에서도 GET만 제공한다.
"""

from datetime import datetime

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.views import APIView

from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdminOrFacilityAdmin
from apps.operations.models.app_log import AppLog
from apps.operations.models.integration_log import IntegrationLog
from apps.operations.serializers import AppLogSerializer, IntegrationLogAdminSerializer


def _parse_date(value: str):
    """
    역할: "YYYY-MM-DD" 문자열을 timezone-aware datetime으로 변환하는 헬퍼.

    왜 별도 함수로 분리하는가:
      AppLog와 IntegrationLog 두 뷰 모두 날짜 파싱이 필요하다.
      같은 로직을 두 번 쓰면 나중에 수정할 때 두 곳을 동시에 바꿔야 한다.
      한 곳에 두면 수정이 한 번으로 끝난다.

    파싱 실패 시 None을 반환하는 이유:
      잘못된 날짜 형식이 들어왔을 때 에러를 발생시키면
      사용자가 날짜 필터만 잘못 입력해도 목록 전체가 안 보인다.
      None을 반환해 해당 필터를 조용히 무시하는 게 UX상 더 낫다.
    """
    if not value:
        return None
    try:
        return timezone.make_aware(datetime.strptime(value.strip(), "%Y-%m-%d"))
    except ValueError:
        return None


# ────────────────────────────────────────────
# 1. 시스템 로그 조회
# ────────────────────────────────────────────


class AppLogAdminListView(APIView):
    """
    GET /api/admin/system-logs/

    왜 "시스템 로그"인데 모델명은 AppLog인가:
      AppLog는 "애플리케이션 운영 로그"를 의미한다.
      화면 설계서에서는 "시스템 로그"로 표현하고,
      사용자 행동 감사는 SystemLog라는 별도 모델로 분리되어 있다.
      URL을 system-logs로 지으면 화면과 API 이름이 일치해 혼란이 없다.
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    @extend_schema(
        tags=["Admin — Logs"],
        summary="시스템 로그 목록 조회",
        description="AppLog 기반. 운영 중 발생한 오류·배치·서비스 로그를 조회한다.",
        parameters=[
            OpenApiParameter(
                name="log_category",
                type=str,
                required=False,
                description="error | batch | service",
            ),
            OpenApiParameter(
                name="level",
                type=str,
                required=False,
                description="ERROR | WARNING | INFO",
            ),
            OpenApiParameter(
                name="keyword",
                type=str,
                required=False,
                description="message 또는 service_module 검색",
            ),
            OpenApiParameter(
                name="date_from", type=str, required=False, description="YYYY-MM-DD"
            ),
            OpenApiParameter(
                name="date_to", type=str, required=False, description="YYYY-MM-DD"
            ),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            200: AppLogSerializer(many=True),
            401: OpenApiResponse(description="인증 필요"),
            403: OpenApiResponse(description="관리자 권한 필요"),
        },
    )
    def get(self, request):
        """
        흐름:
          1. 쿼리 파라미터로 필터 조건 수집
          2. AppLog ORM 쿼리 빌드
          3. AdminPagination으로 페이지 자름
          4. AppLogSerializer로 직렬화
          5. 응답 반환
        """
        qs = AppLog.objects.all()

        # ── 필터 적용 ──────────────────────────────

        log_category = request.query_params.get("log_category", "").strip()
        if log_category:
            valid = [c.value for c in AppLog.LogCategory]
            if log_category in valid:
                qs = qs.filter(log_category=log_category)

        level = request.query_params.get("level", "").strip().upper()
        if level:
            # level은 자유 문자열이라 iexact(대소문자 무시 일치)로 검색
            qs = qs.filter(level__iexact=level)

        keyword = request.query_params.get("keyword", "").strip()
        if keyword:
            # message나 service_module 중 하나라도 포함되면 반환
            # | 연산자: OR 조건. Q객체를 쓰는 이유는 두 필드를 동시에 검색하기 위해서
            from django.db.models import Q

            qs = qs.filter(
                Q(message__icontains=keyword) | Q(service_module__icontains=keyword)
            )

        date_from = _parse_date(request.query_params.get("date_from", ""))
        if date_from:
            qs = qs.filter(created_at__gte=date_from)

        date_to = _parse_date(request.query_params.get("date_to", ""))
        if date_to:
            # 종료일은 해당 날짜의 끝(23:59:59)까지 포함되도록 하루를 더한 후 lt 사용
            # date_to = 2026-04-12 이면 2026-04-13 00:00:00 미만 = 2026-04-12 전체 포함
            from datetime import timedelta

            qs = qs.filter(created_at__lt=date_to + timedelta(days=1))

        # ── 정렬: 최신순 고정 ──────────────────────
        # 로그는 항상 최신순이 기본. 인덱스(idx_applog_time)와 일치해 빠르게 조회된다.
        qs = qs.order_by("-created_at")

        # ── 페이지네이션 + 직렬화 ──────────────────
        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AppLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ────────────────────────────────────────────
# 2. 연동 로그 조회
# ────────────────────────────────────────────


class IntegrationLogAdminListView(APIView):
    """
    GET /api/admin/integration-logs/

    왜 operations 앱에 함께 두는가:
      IntegrationLog 모델이 operations 앱 소속이다.
      모델과 뷰를 같은 앱에 두면 관련 코드가 한 곳에 모여 유지보수가 쉽다.
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    @extend_schema(
        tags=["Admin — Logs"],
        summary="연동 로그 목록 조회",
        description="시스템 간 연동 이력(수집/전송/동기화)을 조회한다.",
        parameters=[
            OpenApiParameter(
                name="integration_type",
                type=str,
                required=False,
                description="collect | transmit | sync",
            ),
            OpenApiParameter(
                name="result",
                type=str,
                required=False,
                description="success | failure | delay",
            ),
            OpenApiParameter(
                name="keyword",
                type=str,
                required=False,
                description="target_system 또는 description 검색",
            ),
            OpenApiParameter(
                name="date_from", type=str, required=False, description="YYYY-MM-DD"
            ),
            OpenApiParameter(
                name="date_to", type=str, required=False, description="YYYY-MM-DD"
            ),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            200: IntegrationLogAdminSerializer(many=True),
            401: OpenApiResponse(description="인증 필요"),
            403: OpenApiResponse(description="관리자 권한 필요"),
        },
    )
    def get(self, request):
        qs = IntegrationLog.objects.all()

        # ── 필터 적용 ──────────────────────────────

        integration_type = request.query_params.get("integration_type", "").strip()
        if integration_type:
            valid = [t.value for t in IntegrationLog.IntegrationType]
            if integration_type in valid:
                qs = qs.filter(integration_type=integration_type)

        result = request.query_params.get("result", "").strip()
        if result:
            valid = [r.value for r in IntegrationLog.Result]
            if result in valid:
                qs = qs.filter(result=result)

        keyword = request.query_params.get("keyword", "").strip()
        if keyword:
            from django.db.models import Q

            qs = qs.filter(
                Q(target_system__icontains=keyword) | Q(description__icontains=keyword)
            )

        date_from = _parse_date(request.query_params.get("date_from", ""))
        if date_from:
            qs = qs.filter(created_at__gte=date_from)

        date_to = _parse_date(request.query_params.get("date_to", ""))
        if date_to:
            from datetime import timedelta

            qs = qs.filter(created_at__lt=date_to + timedelta(days=1))

        qs = qs.order_by("-created_at")

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = IntegrationLogAdminSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
