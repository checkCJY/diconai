"""
notices/views/notice_views.py

공지사항 CRUD API 뷰 3종을 정의한다.

  NoticeListView       — GET 목록 조회 / POST 등록
  NoticeDetailView     — GET 상세 조회 / PATCH 수정 / DELETE 삭제
  NoticeAttachmentView — POST 첨부파일 업로드 / DELETE 첨부파일 삭제

흐름에서 이 파일의 위치:
  HTTP 요청 → urls.py 라우팅 → [이 파일 뷰] → 시리얼라이저 → DB → 응답

권한: IsSuperAdminOrFacilityAdmin
  공지사항은 슈퍼관리자(전사 공지 포함)와 시설관리자(해당 공장 공지) 모두 관리.
  작업자(worker)는 조회만 가능하며 이 API는 관리자 전용.
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdminOrFacilityAdmin
from apps.core.services.audit_service import log_action
from apps.notices.models import Notice, NoticeAttachment
from apps.notices.serializers import (
    NoticeAttachmentSerializer,
    NoticeCreateUpdateSerializer,
    NoticeDetailSerializer,
    NoticeListSerializer,
)


def _get_client_ip(request) -> str | None:
    """
    역할: 요청자의 실제 IP를 추출하는 헬퍼. SystemLog ip_address 기록에 사용.

    X-Forwarded-For를 먼저 보는 이유:
      nginx/로드밸런서를 거치면 REMOTE_ADDR은 프록시 IP가 된다.
      X-Forwarded-For 헤더에 실제 클라이언트 IP가 콤마로 구분되어 들어오므로
      첫 번째 값이 원본 클라이언트 IP다.
    """
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ────────────────────────────────────────────
# 1. 목록 조회 + 등록
# ────────────────────────────────────────────


class NoticeListView(APIView):
    """
    GET  /api/admin/notices/        — 공지사항 목록 (페이지네이션 + 필터)
    POST /api/admin/notices/        — 공지사항 등록
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    @extend_schema(
        tags=["Admin — Notices"],
        summary="공지사항 목록 조회",
        parameters=[
            OpenApiParameter(
                name="category",
                type=str,
                required=False,
                description="general | urgent | maintenance",
            ),
            OpenApiParameter(
                name="keyword",
                type=str,
                required=False,
                description="제목 검색 키워드",
            ),
            OpenApiParameter(
                name="is_pinned",
                type=bool,
                required=False,
                description="상단 고정 여부 필터",
            ),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            200: NoticeListSerializer(many=True),
            401: OpenApiResponse(description="인증 필요"),
            403: OpenApiResponse(description="관리자 권한 필요"),
        },
    )
    def get(self, request):
        """
        흐름:
          1. 쿼리 파라미터로 필터 조건 수집
          2. ORM 쿼리 빌드 (필터 + 정렬)
          3. AdminPagination으로 페이지 자름
          4. NoticeListSerializer로 직렬화
          5. 페이지네이션 응답 반환
        """
        # is_deleted=False: 소프트 삭제된 공지는 목록에서 제외
        qs = (
            Notice.objects.filter(is_deleted=False)
            .select_related("author")
            .prefetch_related("attachments")
        )

        # ── 필터 적용 ──────────────────────────────
        category = request.query_params.get("category", "").strip()
        if category:
            valid_categories = [c.value for c in Notice.Category]
            if category not in valid_categories:
                # 3번: 잘못된 값이면 조용히 무시 대신 400으로 반환
                # 이유: 오타(urgnt 등) 입력 시 전체 목록이 뜨면 클라이언트가 필터가 적용된 줄 오해함
                return Response(
                    {"error": "invalid category", "allowed": valid_categories},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(category=category)

        keyword = request.query_params.get("keyword", "").strip()
        if keyword:
            # icontains: 대소문자 무시 부분 일치 검색
            qs = qs.filter(title__icontains=keyword)

        is_pinned = request.query_params.get("is_pinned", "").strip()
        if is_pinned.lower() == "true":
            qs = qs.filter(is_pinned=True)
        elif is_pinned.lower() == "false":
            qs = qs.filter(is_pinned=False)

        # ── 정렬 ───────────────────────────────────
        # is_pinned 상단 고정 → published_at 최신순
        # 모델 Meta의 인덱스(idx_notice_pinned_published)와 일치시켜 인덱스 활용
        qs = qs.order_by("-is_pinned", "-published_at")

        # ── 페이지네이션 ───────────────────────────
        # AdminPagination: page/page_size 파라미터를 읽어 LIMIT/OFFSET SQL로 변환
        # 결과: { results, total, page, page_size, has_next }
        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)

        serializer = NoticeListSerializer(
            page,
            many=True,
            context={"request": request},  # file_url 절대경로 생성에 필요
        )
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["Admin — Notices"],
        summary="공지사항 등록",
        request=NoticeCreateUpdateSerializer,
        responses={
            201: NoticeDetailSerializer,
            400: OpenApiResponse(description="입력값 오류"),
            401: OpenApiResponse(description="인증 필요"),
            403: OpenApiResponse(description="관리자 권한 필요"),
        },
    )
    def post(self, request):
        """
        흐름:
          1. NoticeCreateUpdateSerializer로 입력값 유효성 검사
          2. 검사 통과 → author, updated_by를 request.user로 주입해 저장
          3. 저장된 객체를 NoticeDetailSerializer로 직렬화해 201 반환
        """
        serializer = NoticeCreateUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            # 유효성 검사 실패 시 어떤 필드가 문제인지 errors로 반환
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # author와 updated_by는 클라이언트가 보내는 게 아니라 서버가 주입
        # → 보안: 클라이언트가 임의 작성자를 지정하는 것을 막음
        notice = serializer.save(
            author=request.user,
            updated_by=request.user,
        )

        # 2번: 공지 등록 행위를 SystemLog에 기록
        log_action(
            actor_id=request.user.pk,
            action_type="notice_create",
            target_model="Notice",
            target_id=notice.pk,
            new_value={"title": notice.title, "category": notice.category},
            description=f"공지사항 등록: {notice.title}",
            ip_address=_get_client_ip(request),
        )

        return Response(
            NoticeDetailSerializer(notice, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# ────────────────────────────────────────────
# 2. 상세 조회 + 수정 + 삭제
# ────────────────────────────────────────────


class NoticeDetailView(APIView):
    """
    GET    /api/admin/notices/{id}/  — 공지사항 상세 조회
    PATCH  /api/admin/notices/{id}/  — 공지사항 수정
    DELETE /api/admin/notices/{id}/  — 공지사항 삭제
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    def _get_notice(self, pk):
        """
        역할: pk로 공지사항을 조회하는 내부 헬퍼.
        get_object_or_404를 쓰는 이유: 없는 id로 요청 시 자동으로 404 반환.
        select_related / prefetch_related: 상세 조회는 author + attachments 모두 필요.
          이를 미리 JOIN으로 가져오지 않으면 author.username 접근 시 추가 쿼리 발생(N+1 문제).
        """
        # is_deleted=False: 소프트 삭제된 공지는 이미 없는 것으로 처리 → 404 반환
        return get_object_or_404(
            Notice.objects.filter(is_deleted=False)
            .select_related("author")
            .prefetch_related("attachments"),
            pk=pk,
        )

    @extend_schema(
        tags=["Admin — Notices"],
        summary="공지사항 상세 조회",
        responses={
            200: NoticeDetailSerializer,
            404: OpenApiResponse(description="공지사항 없음"),
        },
    )
    def get(self, request, pk):
        """
        흐름:
          1. pk로 Notice 조회 (없으면 404)
          2. NoticeDetailSerializer로 직렬화 (첨부파일 포함)
          3. 200 반환
        """
        notice = self._get_notice(pk)
        serializer = NoticeDetailSerializer(notice, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        tags=["Admin — Notices"],
        summary="공지사항 수정",
        request=NoticeCreateUpdateSerializer,
        responses={
            200: NoticeDetailSerializer,
            400: OpenApiResponse(description="입력값 오류"),
            404: OpenApiResponse(description="공지사항 없음"),
        },
    )
    def patch(self, request, pk):
        """
        흐름:
          1. pk로 Notice 조회
          2. partial=True로 NoticeCreateUpdateSerializer 유효성 검사
             partial=True 이유: PATCH는 일부 필드만 수정 가능.
             partial=False(PUT)이면 모든 필드를 보내야 해서 불편함.
          3. updated_by를 request.user로 갱신해 저장
          4. 수정된 객체를 NoticeDetailSerializer로 직렬화해 200 반환
        """
        notice = self._get_notice(pk)

        # 2번: 수정 전 값 스냅샷 — SystemLog old_value에 기록해 변경 이력 추적
        old_value = {
            "title": notice.title,
            "category": notice.category,
            "is_pinned": notice.is_pinned,
        }

        serializer = NoticeCreateUpdateSerializer(
            notice,
            data=request.data,
            partial=True,  # 일부 필드만 수정 허용
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        notice = serializer.save(updated_by=request.user)

        # 2번: 수정 행위를 SystemLog에 기록 (old_value/new_value로 무엇이 바뀌었는지 추적 가능)
        log_action(
            actor_id=request.user.pk,
            action_type="notice_update",
            target_model="Notice",
            target_id=notice.pk,
            old_value=old_value,
            new_value={
                "title": notice.title,
                "category": notice.category,
                "is_pinned": notice.is_pinned,
            },
            description=f"공지사항 수정: {notice.title}",
            ip_address=_get_client_ip(request),
        )

        return Response(
            NoticeDetailSerializer(notice, context={"request": request}).data
        )

    @extend_schema(
        tags=["Admin — Notices"],
        summary="공지사항 삭제",
        responses={
            204: OpenApiResponse(description="삭제 성공"),
            404: OpenApiResponse(description="공지사항 없음"),
        },
    )
    def delete(self, request, pk):
        """
        흐름:
          1. pk로 Notice 조회 (소프트 삭제된 공지는 404)
          2. 소프트 삭제 — is_deleted=True, deleted_at, deleted_by 기록
          3. SystemLog에 삭제 행위 기록
          4. 204 No Content 반환

        소프트 삭제로 전환한 이유:
          관리자가 공지를 삭제했을 때 "누가, 언제, 무엇을 삭제했는가" 추적 가능.
          실수 삭제 시 복구 가능.
          is_active=False는 "비공개 처리"용으로 구분하고,
          is_deleted=True는 "완전 삭제 의도"로 구분.
        """
        notice = self._get_notice(pk)

        # 소프트 삭제: DB에서 제거하지 않고 is_deleted 플래그만 변경
        # update_fields로 지정한 3개 컬럼만 UPDATE — 불필요한 컬럼 갱신 방지
        notice.is_deleted = True
        notice.deleted_at = timezone.now()
        notice.deleted_by = request.user
        notice.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

        # 2번: 삭제 행위를 SystemLog에 기록
        # 소프트 삭제이므로 old_value에 제목/카테고리 스냅샷을 남겨 추후 확인 가능
        log_action(
            actor_id=request.user.pk,
            action_type="notice_delete",
            target_model="Notice",
            target_id=notice.pk,
            old_value={"title": notice.title, "category": notice.category},
            description=f"공지사항 삭제: {notice.title}",
            ip_address=_get_client_ip(request),
        )

        # 204: 성공했지만 반환할 본문이 없음을 의미
        return Response(status=status.HTTP_204_NO_CONTENT)


# ────────────────────────────────────────────
# 3. 첨부파일 업로드 + 삭제
# ────────────────────────────────────────────


class NoticeAttachmentView(APIView):
    """
    POST   /api/admin/notices/{id}/attachments/          — 첨부파일 업로드
    DELETE /api/admin/notices/{id}/attachments/{att_id}/ — 첨부파일 삭제
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    # MultiPartParser: 파일 업로드(multipart/form-data) 요청을 파싱
    # FormParser: 일반 form 데이터 파싱
    # 기본 JSONParser만으로는 파일 업로드가 불가능하므로 추가 필요
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["Admin — Notices"],
        summary="첨부파일 업로드",
        request=inline_serializer(
            name="NoticeAttachmentUploadRequest",
            fields={"file": serializers.FileField()},
        ),
        responses={
            201: NoticeAttachmentSerializer,
            400: OpenApiResponse(description="파일 없음 또는 유효성 오류"),
            404: OpenApiResponse(description="공지사항 없음"),
        },
    )
    def post(self, request, pk):
        """
        흐름:
          1. pk로 Notice 조회 (없으면 404)
          2. request.FILES["file"]로 업로드된 파일 꺼내기
          3. validators(10MB 제한, 확장자 검사)는 모델 필드에서 자동 실행됨
          4. NoticeAttachment 저장
          5. 저장된 첨부파일 정보를 201로 반환

        첨부파일 업로드를 공지사항 등록(POST /notices/)과 분리한 이유:
          - 등록 시 파일을 함께 보내면 요청 구조가 복잡해짐(JSON + 파일 혼합).
          - 파일은 multipart/form-data, 공지 정보는 JSON이 자연스러움.
          - 등록 후 파일을 별도로 추가하는 UX 패턴이 일반적.
        """
        # is_deleted=False: 소프트 삭제된 공지에는 파일 업로드 불가
        notice = get_object_or_404(Notice, pk=pk, is_deleted=False)

        file = request.FILES.get("file")
        if not file:
            return Response(
                {"detail": "file 필드가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attachment = NoticeAttachment(
            notice=notice,
            file=file,
            filename=file.name,  # 원본 파일명 저장 (storage 경로와 별개)
            size=file.size,  # 파일 크기(byte) 저장
            updated_by=request.user,
        )
        # full_clean(): 모델 validators(10MB 제한, 확장자 검사) 명시적 실행
        # save()는 validators를 자동 실행하지 않으므로 명시적으로 호출해야 함
        try:
            attachment.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        attachment.save()

        return Response(
            NoticeAttachmentSerializer(attachment, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=["Admin — Notices"],
        summary="첨부파일 삭제",
        responses={
            204: OpenApiResponse(description="삭제 성공"),
            404: OpenApiResponse(description="첨부파일 없음"),
        },
    )
    def delete(self, request, pk, att_id):
        """
        흐름:
          1. pk(공지사항)와 att_id(첨부파일) 모두 확인
             notice_id=pk 조건을 추가하는 이유:
             다른 공지사항의 첨부파일 id를 넣어도 삭제되는 것을 막기 위함.
          2. storage에서 실제 파일 삭제 + DB 레코드 삭제
          3. 204 반환
        """
        attachment = get_object_or_404(NoticeAttachment, pk=att_id, notice_id=pk)

        # storage의 실제 파일도 함께 삭제
        # Django FileField.delete(save=False): storage 파일 삭제 후 모델은 아직 저장 안 함
        attachment.file.delete(save=False)
        attachment.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
