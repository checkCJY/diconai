"""
operations/views/admin/retention_policy_views.py

데이터 보관 정책 관리자 뷰.

[엔드포인트]
  GET  /api/admin/retention-policies/           — 전체 정책 목록
  GET  /api/admin/retention-policies/{id}/      — 단건 + 현재 삭제 예정 행 수
  PATCH /api/admin/retention-policies/{id}/     — 보관 기간/삭제 주기/활성 여부 수정
  GET  /api/admin/retention-policies/{id}/preview/?raw_days=N
                                                — 특정 일수 기준 삭제 예정 행 수 미리보기

[Preview 엔드포인트 설계 이유]
  보관 기간을 줄이기 전에 "몇 행이 삭제되는지" 관리자가 확인할 수 있어야 한다.
  프론트에서 raw_days 입력값이 바뀔 때마다 호출 — 저장 없이 count만 계산.
  _delete_for_policy(dry_run=True) 를 활용해 실제 쿼리 로직과 동기화 유지.
  SimpleNamespace로 mock policy 전달 — 불필요한 DB 저장 없음.
"""

from types import SimpleNamespace

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsSuperAdminOrFacilityAdmin
from apps.operations.models.data_retention_policy import DataRetentionPolicy
from apps.operations.serializers import DataRetentionPolicySerializer


class DataRetentionPolicyRunView(APIView):
    """
    POST /api/admin/retention-policies/run/

    배치를 즉시 실행하거나 dry_run으로 삭제 예정 행 수를 미리 확인.

    body: { "dry_run": true | false }

    반환: {
      "dry_run": bool,
      "results": [ { "policy_id": N, "category": "...", "category_display": "...", "count": N }, ... ],
      "total": N
    }

    [dry_run=true]  실제 삭제 없이 대상 행 수만 반환 — 미리보기 용도.
    [dry_run=false] 실제 삭제 실행 — 확인창 후 호출.
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    @extend_schema(
        tags=["Admin — 데이터 보관 정책"],
        summary="보관 배치 즉시 실행 (dry_run 지원)",
        request=inline_serializer(
            name="RetentionRunRequest",
            fields={"dry_run": serializers.BooleanField(default=True)},
        ),
        responses=inline_serializer(
            name="RetentionRunResponse",
            fields={
                "dry_run": serializers.BooleanField(),
                "results": serializers.ListField(child=serializers.DictField()),
                "total": serializers.IntegerField(),
            },
        ),
    )
    def post(self, request):
        dry_run = bool(request.data.get("dry_run", True))

        from apps.operations.tasks.data_retention_task import _delete_for_policy

        policies = DataRetentionPolicy.objects.filter(is_active=True)

        results = []
        total = 0
        for policy in policies:
            # 수동 실행(이 API)은 dry_run 여부와 관계없이 delete_cycle 무시.
            # Celery 자동 배치(run_data_retention task)만 cycle 체크.
            try:
                count = _delete_for_policy(policy, dry_run=dry_run)
            except Exception:
                count = None

            results.append(
                {
                    "policy_id": policy.id,
                    "category": policy.data_category,
                    "category_display": policy.get_data_category_display(),
                    "device_type_display": policy.get_device_type_display(),
                    "count": count,
                }
            )
            if count:
                total += count

        return Response({"dry_run": dry_run, "results": results, "total": total})


class DataRetentionPolicyListView(APIView):
    """
    GET /api/admin/retention-policies/

    활성/비활성 포함 전체 정책 목록 반환.
    count는 포함 안 함 — 12개 정책이어도 테이블 scan이 크므로 목록에선 제외,
    편집 모달 열 때 detail 엔드포인트에서 조회.
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    @extend_schema(
        tags=["Admin — 데이터 보관 정책"],
        summary="보관 정책 목록",
        description="데이터 카테고리별 보관 기간·삭제 주기·활성 여부 전체 목록.",
        responses=inline_serializer(
            name="RetentionPolicyListResponse",
            fields={
                "results": DataRetentionPolicySerializer(many=True),
                "count": serializers.IntegerField(),
            },
        ),
    )
    def get(self, request):
        policies = DataRetentionPolicy.objects.all().order_by(
            "device_type", "data_category"
        )
        serializer = DataRetentionPolicySerializer(policies, many=True)
        return Response({"results": serializer.data, "count": policies.count()})


class DataRetentionPolicyDetailView(APIView):
    """
    GET  /api/admin/retention-policies/{id}/ — 단건 + 삭제 예정 행 수
    PATCH /api/admin/retention-policies/{id}/ — 보관 기간/주기/활성 수정
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    @extend_schema(
        tags=["Admin — 데이터 보관 정책"],
        summary="보관 정책 단건 조회 (삭제 예정 행 수 포함)",
        description="편집 모달 진입 시 호출. affected_rows 필드에 현재 기준 삭제 예정 행 수 포함.",
        responses={
            200: DataRetentionPolicySerializer,
            404: OpenApiResponse(description="정책을 찾을 수 없음"),
        },
    )
    def get(self, request, pk):
        policy = get_object_or_404(DataRetentionPolicy, pk=pk)
        serializer = DataRetentionPolicySerializer(policy)
        data = serializer.data

        # 현재 정책 기준 삭제 예정 행 수 — 모달 상단에 노출
        try:
            from apps.operations.tasks.data_retention_task import _delete_for_policy

            data["affected_rows"] = _delete_for_policy(policy, dry_run=True)
        except Exception:
            data["affected_rows"] = None

        return Response(data)

    @extend_schema(
        tags=["Admin — 데이터 보관 정책"],
        summary="보관 정책 수정",
        description=(
            "수정 가능: raw_retention_days, history_retention_days, delete_cycle, is_active, memo. "
            "device_type, data_category는 수정 불가. "
            "history_retention_days < raw_retention_days 이면 400."
        ),
        request=DataRetentionPolicySerializer,
        responses={
            200: DataRetentionPolicySerializer,
            400: OpenApiResponse(description="유효성 오류"),
            404: OpenApiResponse(description="정책을 찾을 수 없음"),
        },
    )
    def patch(self, request, pk):
        policy = get_object_or_404(DataRetentionPolicy, pk=pk)
        original_raw_days = policy.raw_retention_days
        original_history_days = policy.history_retention_days

        serializer = DataRetentionPolicySerializer(
            policy, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        data = serializer.data

        # save() 후 갱신된 값
        new_raw_days = policy.raw_retention_days
        new_history_days = policy.history_retention_days
        data["raw_days_reduced"] = new_raw_days < original_raw_days
        data["history_days_reduced"] = new_history_days < original_history_days

        # 원천 또는 이력 보관 기간 중 하나라도 줄었으면 저장 즉시 초과 데이터 삭제.
        try:
            from apps.operations.tasks.data_retention_task import _delete_for_policy

            if data["raw_days_reduced"] or data["history_days_reduced"]:
                data["affected_rows"] = _delete_for_policy(policy, dry_run=False)
            else:
                data["affected_rows"] = 0
        except Exception:
            data["affected_rows"] = None

        return Response(data)


class DataRetentionPolicyPreviewView(APIView):
    """
    GET /api/admin/retention-policies/{id}/preview/?raw_days=N

    저장 없이 raw_days 기준 삭제 예정 행 수만 반환.
    편집 모달에서 raw_retention_days 입력값이 바뀔 때마다 debounce 호출.
    SimpleNamespace mock으로 _delete_for_policy 재활용 — DB 쿼리 로직 동기화 유지.
    """

    permission_classes = [IsSuperAdminOrFacilityAdmin]

    @extend_schema(
        tags=["Admin — 데이터 보관 정책"],
        summary="보관 기간 변경 미리보기 (삭제 예정 행 수)",
        parameters=[
            OpenApiParameter(
                name="raw_days",
                type=int,
                description="미리볼 원천 보관 기간(일).",
            ),
            OpenApiParameter(
                name="history_days",
                type=int,
                description="미리볼 이력 보관 기간(일). 생략 시 현재 정책값 사용.",
            ),
        ],
        responses=inline_serializer(
            name="RetentionPreviewResponse",
            fields={
                "id": serializers.IntegerField(),
                "raw_days": serializers.IntegerField(),
                "history_days": serializers.IntegerField(),
                "current_raw_days": serializers.IntegerField(),
                "current_history_days": serializers.IntegerField(),
                "affected_rows": serializers.IntegerField(allow_null=True),
                "days_reduced": serializers.BooleanField(),
            },
        ),
    )
    def get(self, request, pk):
        policy = get_object_or_404(DataRetentionPolicy, pk=pk)

        raw_days_str = request.query_params.get("raw_days")
        try:
            raw_days = int(raw_days_str)
            if raw_days < 1:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "raw_days는 1 이상의 정수여야 합니다."}, status=400
            )

        # history_days는 선택 파라미터 — 생략 시 현재 정책값 유지
        history_days_str = request.query_params.get("history_days")
        try:
            history_days = (
                int(history_days_str)
                if history_days_str
                else policy.history_retention_days
            )
            if history_days < 1:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "history_days는 1 이상의 정수여야 합니다."}, status=400
            )

        mock = SimpleNamespace(
            id=policy.id,
            data_category=policy.data_category,
            raw_retention_days=raw_days,
            history_retention_days=history_days,
        )

        try:
            from apps.operations.tasks.data_retention_task import _delete_for_policy

            count = _delete_for_policy(mock, dry_run=True)
        except Exception:
            count = None

        return Response(
            {
                "id": pk,
                "raw_days": raw_days,
                "history_days": history_days,
                "current_raw_days": policy.raw_retention_days,
                "current_history_days": policy.history_retention_days,
                "affected_rows": count,
                "days_reduced": (
                    raw_days < policy.raw_retention_days
                    or history_days < policy.history_retention_days
                ),
            }
        )
