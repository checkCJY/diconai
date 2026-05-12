"""
core/views/system_log_views.py

사용자 활동 로그(SystemLog)와 지도 편집 로그(MAP_ action) 관리자 조회 뷰.

흐름에서 이 파일의 위치:
  HTTP GET 요청 → urls.py 라우팅 → [이 파일] → Serializer → DB → 응답

두 뷰가 같은 모델(SystemLog)을 보는데 왜 뷰를 나눴는가:
  사용자 활동 로그: MAP_ 이외의 모든 action_type, 필터에 result(결과) 포함.
  지도 편집 로그:   MAP_ action_type만, 필터에 result 없이 target_name 검색.
  화면 설계서에서 탭이 다르고 필터 항목도 다르므로 뷰를 분리했다.
  같은 뷰에서 if 분기로 처리하면 나중에 두 화면 중 하나만 수정할 때 의도치 않은
  사이드 이펙트가 생길 수 있다.
"""

from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models.system_log import SystemLog
from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdminOrFacilityAdmin
from apps.core.serializers import SystemLogAdminSerializer

# MAP_ action_type prefix — 지도 편집 로그 식별용
_MAP_PREFIX = "map_"


def _parse_date(value: str):
    """
    "YYYY-MM-DD" 문자열을 timezone-aware datetime으로 변환.
    파싱 실패 시 None 반환 — 잘못된 날짜 형식이 전체 목록을 막으면 안 된다.
    """
    if not value:
        return None
    try:
        return timezone.make_aware(datetime.strptime(value.strip(), "%Y-%m-%d"))
    except ValueError:
        return None


# ────────────────────────────────────────────
# 1. 사용자 활동 로그 조회
# ────────────────────────────────────────────

class SystemLogAdminListView(APIView):
    """
    GET /api/admin/activity-logs/

    MAP_ prefix action은 지도 편집 로그 API(MapEditLogAdminListView)에서 따로 제공하므로
    이 뷰에서는 exclude(action_type__startswith="map_")로 제외한다.

    actor 검색을 username/email 두 필드 모두 검색하는 이유:
      관리자가 이름 대신 로그인 ID(username)나 이메일로 검색할 수 있어야 한다.
      두 조건을 OR로 묶으면 한 번의 입력으로 두 경우를 모두 커버한다.
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    @extend_schema(
        tags=["Admin — Logs"],
        summary="사용자 활동 로그 목록 조회",
        description=(
            "SystemLog 기반. 관리자의 생성·수정·삭제·권한 변경 등 행위 이력을 조회한다. "
            "지도 편집(MAP_ 계열) action은 제외된다."
        ),
        parameters=[
            OpenApiParameter(
                name="actor",
                type=str,
                required=False,
                description="행위자 username 또는 email (부분 일치)",
            ),
            OpenApiParameter(
                name="action_type",
                type=str,
                required=False,
                description="SystemLog.ActionType 코드값 (예: user_create)",
            ),
            OpenApiParameter(
                name="result",
                type=str,
                required=False,
                description="success | failure",
            ),
            OpenApiParameter(
                name="keyword",
                type=str,
                required=False,
                description="description 검색 (부분 일치)",
            ),
            OpenApiParameter(name="date_from", type=str, required=False, description="YYYY-MM-DD"),
            OpenApiParameter(name="date_to", type=str, required=False, description="YYYY-MM-DD"),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            200: SystemLogAdminSerializer(many=True),
            401: OpenApiResponse(description="인증 필요"),
            403: OpenApiResponse(description="관리자 권한 필요"),
        },
    )
    def get(self, request):
        """
        흐름:
          1. MAP_ action 제외 (지도 편집 로그 분리)
          2. 쿼리 파라미터로 필터 조건 수집
          3. SystemLog ORM 쿼리 빌드
          4. AdminPagination으로 페이지 자름
          5. SystemLogAdminSerializer로 직렬화
          6. 응답 반환

        actor_name이 아닌 actor(username/email)로 필터링하는 이유:
          actor_name은 직렬화 단계에서 만들어지는 계산값이라 ORM 필터에 쓸 수 없다.
          실제 DB 컬럼인 actor__username, actor__email로 필터해야 한다.
        """
        # MAP_ action은 별도 API에서 제공 — 이 뷰에서는 제외
        qs = SystemLog.objects.exclude(action_type__startswith=_MAP_PREFIX)

        # ── 필터 적용 ──────────────────────────────

        actor_keyword = request.query_params.get("actor", "").strip()
        if actor_keyword:
            # username OR email 중 하나라도 부분 일치하면 반환
            qs = qs.filter(
                Q(actor__username__icontains=actor_keyword)
                | Q(actor__email__icontains=actor_keyword)
            )

        action_type = request.query_params.get("action_type", "").strip()
        if action_type:
            valid = [a.value for a in SystemLog.ActionType]
            if action_type in valid:
                qs = qs.filter(action_type=action_type)

        result = request.query_params.get("result", "").strip()
        if result:
            valid = [r.value for r in SystemLog.Result]
            if result in valid:
                qs = qs.filter(result=result)

        keyword = request.query_params.get("keyword", "").strip()
        if keyword:
            # description 본문에서 키워드 검색
            qs = qs.filter(description__icontains=keyword)

        date_from = _parse_date(request.query_params.get("date_from", ""))
        if date_from:
            qs = qs.filter(created_at__gte=date_from)

        date_to = _parse_date(request.query_params.get("date_to", ""))
        if date_to:
            qs = qs.filter(created_at__lt=date_to + timedelta(days=1))

        # ── 정렬: 최신순 고정 ──────────────────────
        qs = qs.order_by("-created_at")

        # ── 페이지네이션 + 직렬화 ──────────────────
        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = SystemLogAdminSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ────────────────────────────────────────────
# 2. 지도 편집 로그 조회
# ────────────────────────────────────────────

class MapEditLogAdminListView(APIView):
    """
    GET /api/admin/map-edit-logs/

    왜 SystemLog를 별도 모델로 분리하지 않았는가:
      지도 편집 행위는 MAP_ prefix action_type으로 SystemLog에 이미 기록된다.
      별도 테이블을 만들면 같은 이벤트가 두 테이블에 중복 저장되는 문제가 생기고,
      audit trail 일관성도 깨진다.
      action_type__startswith="map_" 필터 하나로 지도 편집 로그만 추출할 수 있다.
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    # MAP_ action_type 유효값 목록 — 필터 검증에 사용
    _MAP_ACTION_TYPES = [
        a.value for a in SystemLog.ActionType
        if a.value.startswith(_MAP_PREFIX)
    ]

    @extend_schema(
        tags=["Admin — Logs"],
        summary="지도 편집 로그 목록 조회",
        description=(
            "SystemLog 중 MAP_ 계열 action_type만 반환한다. "
            "(map_geofence_create / map_sensor_move / map_facility_update / "
            "map_position_node_register / map_object_delete)"
        ),
        parameters=[
            OpenApiParameter(
                name="actor",
                type=str,
                required=False,
                description="행위자 username 또는 email (부분 일치)",
            ),
            OpenApiParameter(
                name="action_type",
                type=str,
                required=False,
                description=(
                    "map_geofence_create | map_sensor_move | map_facility_update | "
                    "map_position_node_register | map_object_delete"
                ),
            ),
            OpenApiParameter(
                name="keyword",
                type=str,
                required=False,
                description="target_name 또는 description 검색 (부분 일치)",
            ),
            OpenApiParameter(name="date_from", type=str, required=False, description="YYYY-MM-DD"),
            OpenApiParameter(name="date_to", type=str, required=False, description="YYYY-MM-DD"),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            200: SystemLogAdminSerializer(many=True),
            401: OpenApiResponse(description="인증 필요"),
            403: OpenApiResponse(description="관리자 권한 필요"),
        },
    )
    def get(self, request):
        """
        흐름:
          1. MAP_ action만 포함
          2. action_type 필터 (MAP_ 내에서 세부 유형 선택)
          3. actor / keyword(target_name + description) / date 필터
          4. AdminPagination + SystemLogAdminSerializer
        """
        # MAP_ prefix인 action_type만 — 지도 편집 이외는 제외
        qs = SystemLog.objects.filter(action_type__startswith=_MAP_PREFIX)

        # ── 필터 적용 ──────────────────────────────

        actor_keyword = request.query_params.get("actor", "").strip()
        if actor_keyword:
            qs = qs.filter(
                Q(actor__username__icontains=actor_keyword)
                | Q(actor__email__icontains=actor_keyword)
            )

        action_type = request.query_params.get("action_type", "").strip()
        if action_type:
            # MAP_ 외의 값이 들어오면 조용히 무시 (존재하지 않는 유형이 결과 0건을 반환하는 것 방지)
            if action_type in self._MAP_ACTION_TYPES:
                qs = qs.filter(action_type=action_type)

        keyword = request.query_params.get("keyword", "").strip()
        if keyword:
            # target_name(지도 객체 이름)과 description 둘 다 검색
            qs = qs.filter(
                Q(target_name__icontains=keyword) | Q(description__icontains=keyword)
            )

        date_from = _parse_date(request.query_params.get("date_from", ""))
        if date_from:
            qs = qs.filter(created_at__gte=date_from)

        date_to = _parse_date(request.query_params.get("date_to", ""))
        if date_to:
            qs = qs.filter(created_at__lt=date_to + timedelta(days=1))

        # ── 정렬: 최신순 고정 ──────────────────────
        qs = qs.order_by("-created_at")

        # ── 페이지네이션 + 직렬화 ──────────────────
        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = SystemLogAdminSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
