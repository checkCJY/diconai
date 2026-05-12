"""
apps/training/views/admin_views.py — VR 교육 관리 어드민 API.

[엔드포인트 — Plan §4]
- GET   /api/admin/training/vr-training/                 facility별 단일 콘텐츠 조회
- POST  /api/admin/training/vr-training/replace/         multipart 영상 교체 (자동 duration)
- PATCH /api/admin/training/vr-training/<pk>/            메타만 수정 (파일 미수반)
- GET   /api/admin/training/vr-training/<pk>/revisions/  교체 이력 (UI 미사용, API 완비)

[facility 해석] safety 어드민과 동일 패턴(_resolve_facility_id).
[권한] IsAuthenticated + IsSuperAdminOrFacilityAdmin.
[CLAUDE.md] view는 권한·검증·서비스 호출만. 비즈니스 로직은 services 레이어.
"""

import logging
import os
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.constants import UserType
from apps.core.permissions import IsSuperAdminOrFacilityAdmin
from apps.facilities.models.facility import Facility
from apps.facilities.selectors.facility import get_default_facility_id
from apps.training.models import VRTrainingContent
from apps.training.serializers.vr_admin import (
    VRContentDetailSerializer,
    VRMetaUpdateSerializer,
    VRRevisionListSerializer,
    VRVideoUploadSerializer,
)
from apps.training.services import vr_admin_service as svc
from apps.training.services.ffprobe import probe_duration_seconds

logger = logging.getLogger(__name__)


def _resolve_facility_id(request) -> int | None:
    """요청에서 대상 facility를 결정.

    [정책 — safety 어드민과 동일]
    1) SUPER_ADMIN: ?facility_id=쿼리 우선 → 본인 facility_id → 첫 활성 facility
    2) FACILITY_ADMIN: 본인 facility_id → 첫 활성 facility (단일 공장 폴백)

    단일 공장 운영 단계에서 user.facility_id가 NULL인 super_admin이 페이지에
    진입했을 때 곧바로 동작하도록 마지막에 `get_default_facility_id()` 폴백.
    다중 공장 전환 시 FACILITY_ADMIN 폴백은 데이터 노출 위험이 있어 제거 후
    명시 지정으로 전환해야 한다.

    Returns:
        해석된 facility_id. 활성 facility가 한 건도 없으면 None.
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


def _facility_required_response() -> Response:
    """`_resolve_facility_id`가 None을 반환한 경우의 표준 400 응답."""
    return Response(
        {"detail": "facility_id가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
    )


def _empty_response(facility_id: int) -> Response:
    """해당 facility에 콘텐츠가 한 번도 등록되지 않은 상태의 응답.

    화면이 '[영상 교체] 버튼을 눌러 첫 콘텐츠를 등록해 주세요' 안내를 그릴
    수 있도록 `empty=True` 플래그와 facility 메타만 반환.
    """
    facility = Facility.objects.filter(pk=facility_id).only("id", "name").first()
    return Response(
        {
            "empty": True,
            "facility_id": facility_id,
            "facility_name": facility.name if facility else None,
        }
    )


# ──────────────────────────────────────────────────────────
# GET /vr-training/
# ──────────────────────────────────────────────────────────
class VRTrainingDetailView(APIView):
    """facility별 활성 단일 VR 콘텐츠 조회.

    [응답 분기]
    - 콘텐츠 있음: `VRContentDetailSerializer` 정상 응답
    - 콘텐츠 없음: `{empty: true, facility_id, facility_name}` — 화면 빈 상태용

    [super_admin 다른 공장 조회]
    `?facility_id=` 쿼리로 다른 공장 콘텐츠 조회 가능. 시설관리자는 본인
    facility에 강제 매핑되어 쿼리 파라미터가 무시된다.
    """

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — VR Training"],
        summary="VR 교육 단일 콘텐츠 조회 (facility별)",
        responses={
            200: VRContentDetailSerializer,
            400: OpenApiResponse(description="facility_id 없음"),
        },
    )
    def get(self, request):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        content = svc.get_vr_content_for_facility(facility_id)
        if content is None:
            return _empty_response(facility_id)
        return Response(VRContentDetailSerializer(content).data)


# ──────────────────────────────────────────────────────────
# POST /vr-training/replace/
# ──────────────────────────────────────────────────────────
class VRTrainingReplaceView(APIView):
    """영상 교체 또는 최초 등록 — multipart 업로드.

    [요청 처리 흐름]
    1) facility_id 해석 + 파일/메타 검증
    2) 트랜잭션 진입 전 `default_storage.save`로 새 파일 저장
    3) `probe_duration_seconds`로 ffprobe 호출 (실패 시 None fallback)
    4) `request.build_absolute_uri`로 절대 URL 구성 → `content_url`에 기록
    5) `replace_vr_content` 서비스 호출 (DB만 트랜잭션, 파일 삭제는 on_commit)
    6) service 예외 발생 시 새로 저장한 파일을 청소 후 재전파

    [트랜잭션 경계가 service인 이유]
    파일 I/O는 트랜잭션 밖에서 수행해야 롤백 시 파일 상태가 망가지지 않는다.
    View가 파일을 먼저 저장하고, service가 DB 작업만 transaction.atomic으로
    감싼다.

    [200 OK with warning 패턴 미사용]
    duration 추출 실패는 응답에 별도 경고 키 없이 단순히 `duration_seconds: null`로
    반환. 클라이언트는 `<video>.loadedmetadata`로 시간 표시를 보강 가능.
    """

    permission_classes = _BASE_PERMS
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["Admin — VR Training"],
        summary="영상 교체 — multipart 업로드, duration 자동 추출",
        request=VRVideoUploadSerializer,
        responses={200: VRContentDetailSerializer},
    )
    def post(self, request):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()

        serializer = VRVideoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data["file"]
        name = serializer.validated_data.get("name")
        description = serializer.validated_data.get("description")
        operation_note = serializer.validated_data.get("operation_note")

        # 1) 트랜잭션 진입 전 파일 저장 — 실패 시 DB 무변경.
        ext = (uploaded.name or "").rsplit(".", 1)[-1].lower()
        stored_relpath = f"vr/{uuid.uuid4().hex}.{ext}"
        saved_name = default_storage.save(stored_relpath, uploaded)
        abs_path = os.path.join(settings.MEDIA_ROOT, saved_name)

        # 2) 재생 시간 추출 (실패해도 진행).
        duration = probe_duration_seconds(abs_path)

        # 3) 절대 URL 구성 (URLField 검증 통과를 위해).
        new_url = request.build_absolute_uri(settings.MEDIA_URL + saved_name)

        existing = svc.get_vr_content_for_facility(facility_id)
        try:
            content = svc.replace_vr_content(
                content=existing,
                facility_id=facility_id,
                new_content_url=new_url,
                duration_seconds=duration,
                name=name,
                description=description,
                operation_note=operation_note,
                user=request.user,
            )
        except Exception:
            # 새로 저장한 파일은 청소하고 예외 재전파.
            try:
                default_storage.delete(saved_name)
            except OSError:
                logger.warning("업로드 롤백 중 파일 삭제 실패: %s", saved_name)
            raise

        return Response(VRContentDetailSerializer(content).data)


# ──────────────────────────────────────────────────────────
# PATCH /vr-training/<pk>/
# ──────────────────────────────────────────────────────────
class VRTrainingMetaUpdateView(APIView):
    """영상 파일을 동반하지 않는 메타 수정 (이름/설명/운영 메모).

    [권한 가드]
    `pk + facility_id` AND 조건으로 조회 → 다른 공장 콘텐츠의 pk를 직접
    지정해도 404로 거부. facility 간 격리를 URL 레벨에서 강제.
    """

    permission_classes = _BASE_PERMS

    def _get_content(self, request, pk):
        """대상 콘텐츠 1건 조회. 권한 가드를 거친 결과를 반환.

        Returns:
            (content, facility_id) 튜플.
            - facility_id가 None이면 호출부가 400 응답
            - content가 None이면 호출부가 404 응답
        """
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return None, None
        try:
            content = VRTrainingContent.objects.select_related(
                "target_facility", "updated_by"
            ).get(pk=pk, target_facility_id=facility_id, is_active=True)
        except VRTrainingContent.DoesNotExist:
            return None, facility_id
        return content, facility_id

    @extend_schema(
        tags=["Admin — VR Training"],
        summary="VR 메타 수정 (영상 미수반)",
        request=VRMetaUpdateSerializer,
        responses={200: VRContentDetailSerializer},
    )
    def patch(self, request, pk):
        content, facility_id = self._get_content(request, pk)
        if facility_id is None:
            return _facility_required_response()
        if content is None:
            return Response(
                {"detail": "콘텐츠를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = VRMetaUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        content = svc.update_vr_metadata(
            content=content,
            name=serializer.validated_data.get("name"),
            description=serializer.validated_data.get("description"),
            operation_note=serializer.validated_data.get("operation_note"),
            user=request.user,
        )
        return Response(VRContentDetailSerializer(content).data)


# ──────────────────────────────────────────────────────────
# GET /vr-training/<pk>/revisions/
# ──────────────────────────────────────────────────────────
class VRTrainingRevisionListView(APIView):
    """VR 콘텐츠 교체 이력 리스트.

    [현재 UI 미사용]
    화면에는 노출하지 않지만 산재 감사 요건상 "언제·누가 교체했는가"를
    추적 가능하도록 API는 완비해 둔다. 추후 어드민 모달이 추가될 때 그대로 사용.

    [권한 가드]
    `pk + facility_id` AND 조건으로 콘텐츠 존재 확인 후 revisions만 직렬화.
    다른 공장 콘텐츠의 이력에 접근하려는 시도는 404.
    """

    permission_classes = _BASE_PERMS

    @extend_schema(
        tags=["Admin — VR Training"],
        summary="교체 이력 리스트",
        responses={200: VRRevisionListSerializer(many=True)},
    )
    def get(self, request, pk):
        facility_id = _resolve_facility_id(request)
        if facility_id is None:
            return _facility_required_response()
        if not VRTrainingContent.objects.filter(
            pk=pk, target_facility_id=facility_id
        ).exists():
            return Response(
                {"detail": "콘텐츠를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        revisions = (
            VRTrainingContent.objects.get(pk=pk)
            .revisions.select_related("replaced_by")
            .order_by("-replaced_at")
        )
        return Response(VRRevisionListSerializer(revisions, many=True).data)
