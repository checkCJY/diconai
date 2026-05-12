# safety/views/admin_views.py
"""
안전 점검 체크리스트 API — 어드민 11종 + 운영자 공용 1종.

[책임 분리]
- 어드민 (`/api/admin/safety/...`): 슈퍼관리자·시설관리자 한정. 섹션/문항 CRUD,
  순서 변경, 발행, 이력 조회.
- 운영자 공용 (`/api/safety/checklist/active/`): 인증된 사용자 누구나. 활성
  Revision의 스냅샷만 read-only로 반환 (작업자 페이지 렌더링용).

[facility 해석 정책 — `_resolve_facility_id`]
1) SUPER_ADMIN: `?facility_id=` 쿼리/바디 > 본인 facility_id > 기본(첫 활성) facility
2) FACILITY_ADMIN: 본인 facility_id > 기본 facility (단일 공장 가정용 폴백)
단일 공장 환경의 UX 안전망으로 폴백을 둠. 다중 공장 전환 시 FACILITY_ADMIN
폴백은 데이터 노출 위험이 있어 제거 후 명시 지정 필요 (후속 과제).

[CLAUDE.md 컨벤션 준수]
view는 권한 체크 → serializer 검증 → services 호출만 담당. 비즈니스 로직은
`services/checklist_admin_service.py`로 분리.
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.constants import UserType
from apps.core.permissions import IsSuperAdminOrFacilityAdmin
from apps.facilities.selectors.facility import get_default_facility_id
from apps.safety.models import SafetyCheckItem, SafetyCheckSection
from apps.safety.selectors.checklist import (
    get_active_revision,
    get_revision,
    get_sections_with_items,
    has_unpublished_changes,
    list_revisions,
)
from apps.safety.serializers.checklist_admin import (
    ChecklistItemCreateSerializer,
    ChecklistItemReorderSerializer,
    ChecklistItemUpdateSerializer,
    ChecklistReorderSerializer,
    ChecklistSectionCreateSerializer,
    ChecklistSectionSerializer,
    ChecklistSectionUpdateSerializer,
    ChecklistStateSerializer,
    RevisionDetailSerializer,
    RevisionListItemSerializer,
)
from apps.safety.services import checklist_admin_service as svc


def _resolve_facility_id(request) -> int | None:
    """
    슈퍼관리자: ?facility_id= 쿼리 우선 → 본인 facility_id → 기본(첫 활성) facility
    시설관리자: 본인 facility_id → 기본(첫 활성) facility

    단일 공장 운영 단계에서 user.facility_id가 NULL이어도 페이지가 즉시 동작하도록
    `get_default_facility_id()`로 마지막 폴백을 수행한다.
    """
    user = request.user
    if user.user_type == UserType.SUPER_ADMIN:
        raw = request.query_params.get("facility_id") or request.data.get("facility_id")
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
        return user.facility_id or get_default_facility_id()
    return user.facility_id or get_default_facility_id()


_BASE_PERMS = [IsAuthenticated, IsSuperAdminOrFacilityAdmin]


def _facility_required_response():
    return Response(
        {"detail": "facility_id가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
    )


# ──────────────────────────────────────────────────────────
# GET /api/safety/checklist/active/  (운영자 공용)
# ──────────────────────────────────────────────────────────
class ActiveChecklistView(APIView):
    """현장 운영자 페이지(/dashboard/safety/checklist/) 용 활성 체크리스트 조회."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Safety"],
        summary="현재 active 체크리스트 (운영자 공용)",
        description=(
            "사용자의 facility_id 기준 활성 SafetyChecklistRevision의 스냅샷을 반환한다. "
            "super_admin은 ?facility_id= 쿼리로 다른 공장 조회 가능."
        ),
        responses={
            200: OpenApiResponse(description="active revision 스냅샷"),
            404: OpenApiResponse(description="활성 체크리스트 없음"),
        },
    )
    def get(self, request):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return Response(
                {"detail": "소속 공장이 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        active = get_active_revision(facility_id)
        if active is None:
            return Response(
                {"detail": "활성 체크리스트가 없습니다.", "code": "no_active_revision"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "version": active.version,
                "published_at": active.published_at,
                "facility_id": facility_id,
                "sections": (active.revision_data or {}).get("sections", []),
            }
        )


# ──────────────────────────────────────────────────────────
# GET /checklist/state/
# ──────────────────────────────────────────────────────────
class ChecklistStateView(APIView):
    """어드민 페이지 헤더용 메타 — 최근 반영일/발행자/편집 중 배지 활성화 신호."""

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="체크리스트 헤더 메타 (최근 반영일, 편집 중 여부)",
        responses={200: ChecklistStateSerializer},
    )
    def get(self, request):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        active = get_active_revision(facility_id)
        published_by = active.published_by if active else None
        data = {
            "facility_id": facility_id,
            "last_published_at": active.published_at if active else None,
            "last_published_by": (
                (getattr(published_by, "name", None) or published_by.get_username())
                if published_by
                else None
            ),
            "last_version": active.version if active else None,
            "has_unpublished_changes": has_unpublished_changes(facility_id),
        }
        return Response(ChecklistStateSerializer(data).data)


# ──────────────────────────────────────────────────────────
# GET/POST /sections/
# ──────────────────────────────────────────────────────────
class ChecklistSectionListView(APIView):
    """GET: 좌측 패널 + 우측 편집기에 동시 사용되는 섹션·문항 트리. POST: 섹션 신규."""

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="섹션 + 문항 트리 조회",
        responses={200: ChecklistSectionSerializer(many=True)},
    )
    def get(self, request):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        sections = get_sections_with_items(facility_id)
        return Response(ChecklistSectionSerializer(sections, many=True).data)

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="섹션 신규 추가",
        request=ChecklistSectionCreateSerializer,
        responses={201: ChecklistSectionSerializer},
    )
    def post(self, request):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        serializer = ChecklistSectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        section = svc.create_section(
            facility_id=facility_id,
            name=serializer.validated_data["name"],
            description=serializer.validated_data.get("description", ""),
            updated_by=request.user,
        )
        return Response(
            ChecklistSectionSerializer(section).data, status=status.HTTP_201_CREATED
        )


# ──────────────────────────────────────────────────────────
# PATCH/DELETE /sections/<id>/
# ──────────────────────────────────────────────────────────
class ChecklistSectionDetailView(APIView):
    """섹션 단건 수정/삭제. 삭제는 soft-delete + 하위 문항 cascade."""

    permission_classes = _BASE_PERMS

    def _get_section(self, request, pk):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return None, None
        try:
            section = SafetyCheckSection.objects.get(
                pk=pk, facility_id=facility_id, is_active=True
            )
        except SafetyCheckSection.DoesNotExist:
            return None, facility_id
        return section, facility_id

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="섹션 수정",
        request=ChecklistSectionUpdateSerializer,
        responses={200: ChecklistSectionSerializer},
    )
    def patch(self, request, pk):
        section, facility_id = self._get_section(request, pk)
        if facility_id is None:
            return _facility_required_response()
        if section is None:
            return Response(
                {"detail": "섹션을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = ChecklistSectionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        section = svc.update_section(
            section,
            name=serializer.validated_data.get("name"),
            description=serializer.validated_data.get("description"),
            updated_by=request.user,
        )
        return Response(ChecklistSectionSerializer(section).data)

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="섹션 비활성화 (Soft Delete) — 하위 문항도 함께 비활성화",
        responses={204: OpenApiResponse(description="삭제 완료")},
    )
    def delete(self, request, pk):
        section, facility_id = self._get_section(request, pk)
        if facility_id is None:
            return _facility_required_response()
        if section is None:
            return Response(
                {"detail": "섹션을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        svc.soft_delete_section(section, updated_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ──────────────────────────────────────────────────────────
# POST /sections/reorder/
# ──────────────────────────────────────────────────────────
class ChecklistSectionReorderView(APIView):
    """드래그앤드롭 후 호출. `ordered_ids` 인덱스 기준으로 일괄 order 갱신."""

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="섹션 순서 변경",
        request=ChecklistReorderSerializer,
        responses={200: OpenApiResponse(description="ok")},
    )
    def post(self, request):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        serializer = ChecklistReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        svc.reorder_sections(facility_id, serializer.validated_data["ordered_ids"])
        return Response({"ok": True})


# ──────────────────────────────────────────────────────────
# POST /sections/<id>/items/
# ──────────────────────────────────────────────────────────
class ChecklistItemCreateView(APIView):
    """선택 섹션에 문항 추가. 응답은 해당 섹션 전체 트리(클라이언트 재렌더용)."""

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="문항 추가",
        request=ChecklistItemCreateSerializer,
        responses={201: ChecklistSectionSerializer},
    )
    def post(self, request, section_id):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        try:
            section = SafetyCheckSection.objects.get(
                pk=section_id, facility_id=facility_id, is_active=True
            )
        except SafetyCheckSection.DoesNotExist:
            return Response(
                {"detail": "섹션을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = ChecklistItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        svc.create_item(
            section=section,
            title=serializer.validated_data["title"],
            description=serializer.validated_data.get("description", ""),
            is_required=serializer.validated_data.get("is_required", True),
            updated_by=request.user,
        )
        return Response(
            ChecklistSectionSerializer(section).data, status=status.HTTP_201_CREATED
        )


# ──────────────────────────────────────────────────────────
# PATCH/DELETE /items/<id>/
# ──────────────────────────────────────────────────────────
class ChecklistItemDetailView(APIView):
    """문항 단건 수정/삭제. 삭제는 soft-delete (이력 보존)."""

    permission_classes = _BASE_PERMS

    def _get_item(self, request, pk):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return None, None
        try:
            item = SafetyCheckItem.objects.get(
                pk=pk, facility_id=facility_id, is_active=True
            )
        except SafetyCheckItem.DoesNotExist:
            return None, facility_id
        return item, facility_id

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="문항 수정",
        request=ChecklistItemUpdateSerializer,
        responses={200: ChecklistSectionSerializer},
    )
    def patch(self, request, pk):
        item, facility_id = self._get_item(request, pk)
        if facility_id is None:
            return _facility_required_response()
        if item is None:
            return Response(
                {"detail": "문항을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = ChecklistItemUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        svc.update_item(
            item,
            title=serializer.validated_data.get("title"),
            description=serializer.validated_data.get("description"),
            is_required=serializer.validated_data.get("is_required"),
            updated_by=request.user,
        )
        return Response(ChecklistSectionSerializer(item.section).data)

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="문항 비활성화 (Soft Delete)",
        responses={204: OpenApiResponse(description="삭제 완료")},
    )
    def delete(self, request, pk):
        item, facility_id = self._get_item(request, pk)
        if facility_id is None:
            return _facility_required_response()
        if item is None:
            return Response(
                {"detail": "문항을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        svc.soft_delete_item(item, updated_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ──────────────────────────────────────────────────────────
# POST /items/<id>/duplicate/
# ──────────────────────────────────────────────────────────
class ChecklistItemDuplicateView(APIView):
    """원본 바로 다음 순번에 동일 문항 사본 생성. 이후 항목은 order 한 칸씩 밀림."""

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="문항 복제 (같은 섹션 내 바로 다음 순번)",
        request=None,
        responses={201: ChecklistSectionSerializer},
    )
    def post(self, request, pk):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        try:
            item = SafetyCheckItem.objects.get(
                pk=pk, facility_id=facility_id, is_active=True
            )
        except SafetyCheckItem.DoesNotExist:
            return Response(
                {"detail": "문항을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        svc.duplicate_item(item, updated_by=request.user)
        return Response(
            ChecklistSectionSerializer(item.section).data,
            status=status.HTTP_201_CREATED,
        )


# ──────────────────────────────────────────────────────────
# POST /items/reorder/
# ──────────────────────────────────────────────────────────
class ChecklistItemReorderView(APIView):
    """드래그앤드롭 결과 반영. section_id 검증 후 ordered_ids 인덱스로 order 갱신."""

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="문항 순서 변경",
        request=ChecklistItemReorderSerializer,
        responses={200: OpenApiResponse(description="ok")},
    )
    def post(self, request):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        serializer = ChecklistItemReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        section_id = serializer.validated_data["section_id"]
        if not SafetyCheckSection.objects.filter(
            pk=section_id, facility_id=facility_id
        ).exists():
            return Response(
                {"detail": "섹션을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        svc.reorder_items(section_id, serializer.validated_data["ordered_ids"])
        return Response({"ok": True})


# ──────────────────────────────────────────────────────────
# POST /checklist/publish/
# ──────────────────────────────────────────────────────────
class ChecklistPublishView(APIView):
    """[반영 저장]: 현재 section/item 상태를 active SafetyChecklistRevision 스냅샷으로 발행.

    노-옵 발행을 방지하기 위해 서비스 레이어가 직전 active와 비교해 동일하면
    `NoChangesToPublishError`를 발생시키며, 본 view는 이를 400 + `code:no_changes`로
    응답해 클라이언트가 "반영 보류" 안내를 표시할 수 있게 한다.
    """

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="반영 저장 — 현재 섹션/문항 상태를 스냅샷으로 발행",
        request=None,
        responses={
            201: RevisionDetailSerializer,
            400: OpenApiResponse(description="변경 사항 없음 (active revision과 동일)"),
        },
    )
    def post(self, request):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        try:
            revision = svc.publish_revision(facility_id=facility_id, user=request.user)
        except svc.NoChangesToPublishError as exc:
            return Response(
                {"detail": str(exc), "code": "no_changes"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            RevisionDetailSerializer(revision).data, status=status.HTTP_201_CREATED
        )


# ──────────────────────────────────────────────────────────
# GET /checklist/revisions/
# ──────────────────────────────────────────────────────────
class ChecklistRevisionListView(APIView):
    """반영 이력 모달 좌측의 일시 리스트(신규순). detail은 별도 view 호출."""

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="반영 이력 (일시) 리스트",
        responses={200: RevisionListItemSerializer(many=True)},
    )
    def get(self, request):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        revisions = list_revisions(facility_id)
        return Response(RevisionListItemSerializer(revisions, many=True).data)


# ──────────────────────────────────────────────────────────
# GET /checklist/revisions/<id>/
# ──────────────────────────────────────────────────────────
class ChecklistRevisionDetailView(APIView):
    """반영 이력 모달 우측의 스냅샷 읽기. 직전 버전 대비 변경 요약(`change_summary`) 동봉."""

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — Safety Checklist"],
        summary="특정 시점 스냅샷 (읽기 전용)",
        responses={200: RevisionDetailSerializer},
    )
    def get(self, request, pk):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        revision = get_revision(pk, facility_id)
        if revision is None:
            return Response(
                {"detail": "개정을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(RevisionDetailSerializer(revision).data)
