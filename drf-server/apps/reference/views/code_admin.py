"""reference/views/code_admin.py

공통 코드 관리 어드민 API 뷰.

[URL 구조]
GET/POST   /api/admin/code-groups/                      — 그룹 목록 / 그룹 생성
PATCH/DEL  /api/admin/code-groups/<id>/                 — 그룹 수정 / 그룹 삭제
GET/POST   /api/admin/code-groups/<id>/codes/           — 코드 목록 / 코드 생성
PATCH/DEL  /api/admin/codes/<id>/                       — 코드 수정 / 코드 삭제
POST       /api/admin/codes/bulk-deactivate/            — 코드 일괄 미사용 전환

[삭제 정책]
그룹 삭제: 하위 CommonCode 가 있으면 400 차단 (임계치 그룹과 동일 PROTECT 정책).
코드 삭제: 개별 삭제는 허용. 일괄은 bulk-deactivate(미사용 전환) 사용.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsSuperAdmin
from apps.reference.models.code_group import CodeGroup
from apps.reference.models.common_code import CommonCode
from apps.reference.serializers.code_admin import (
    CodeGroupSerializer,
    CodeGroupWriteSerializer,
    CommonCodeSerializer,
    CommonCodeWriteSerializer,
)


class CodeGroupAdminListView(APIView):
    """GET  /api/admin/code-groups/ — 그룹 목록 (이름·코드 검색 지원)
    POST /api/admin/code-groups/ — 그룹 생성
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        qs = CodeGroup.objects.all()

        # ?q= 파라미터로 그룹명 또는 그룹코드 부분 검색
        q = request.query_params.get("q")
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)

        serializer = CodeGroupSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CodeGroupWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        group = serializer.save()
        return Response(CodeGroupSerializer(group).data, status=status.HTTP_201_CREATED)


class CodeGroupAdminDetailView(APIView):
    """PATCH  /api/admin/code-groups/<id>/ — 그룹 수정
    DELETE /api/admin/code-groups/<id>/ — 그룹 삭제

    삭제 시 PROTECT 정책: 하위 CommonCode 가 있으면 400 반환.
    """

    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        try:
            return CodeGroup.objects.get(pk=pk)
        except CodeGroup.DoesNotExist:
            return None

    def patch(self, request, pk):
        group = self._get(pk)
        if not group:
            return Response({"detail": "코드 그룹을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CodeGroupWriteSerializer(group, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        group = serializer.save()
        return Response(CodeGroupSerializer(group).data)

    def delete(self, request, pk):
        group = self._get(pk)
        if not group:
            return Response({"detail": "코드 그룹을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        # 하위 코드가 있으면 삭제 차단 — 먼저 코드를 모두 삭제해야 함
        if group.codes.exists():
            return Response(
                {"detail": "코드 값이 있는 그룹은 삭제할 수 없습니다. 먼저 코드를 모두 삭제하세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommonCodeAdminListView(APIView):
    """GET  /api/admin/code-groups/<group_id>/codes/ — 코드 목록
    POST /api/admin/code-groups/<group_id>/codes/ — 코드 생성
    """

    permission_classes = [IsSuperAdmin]

    def _get_group(self, group_id):
        try:
            return CodeGroup.objects.get(pk=group_id)
        except CodeGroup.DoesNotExist:
            return None

    def get(self, request, group_id):
        group = self._get_group(group_id)
        if not group:
            return Response({"detail": "코드 그룹을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        # sort_order → code 순으로 정렬 (모델 Meta.ordering 와 동일)
        qs = CommonCode.objects.filter(group=group)
        serializer = CommonCodeSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request, group_id):
        group = self._get_group(group_id)
        if not group:
            return Response({"detail": "코드 그룹을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CommonCodeWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # group 은 URL 에서 결정 — 클라이언트가 지정 불가
        code = serializer.save(group=group)
        return Response(CommonCodeSerializer(code).data, status=status.HTTP_201_CREATED)


class CommonCodeAdminDetailView(APIView):
    """PATCH  /api/admin/codes/<id>/ — 코드 수정
    DELETE /api/admin/codes/<id>/ — 코드 삭제
    """

    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        try:
            return CommonCode.objects.get(pk=pk)
        except CommonCode.DoesNotExist:
            return None

    def patch(self, request, pk):
        code = self._get(pk)
        if not code:
            return Response({"detail": "코드를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CommonCodeWriteSerializer(code, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.save()
        return Response(CommonCodeSerializer(code).data)

    def delete(self, request, pk):
        code = self._get(pk)
        if not code:
            return Response({"detail": "코드를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        code.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommonCodeBulkDeactivateView(APIView):
    """POST /api/admin/codes/bulk-deactivate/

    선택된 코드들을 일괄 미사용으로 전환한다.
    body: { "ids": [1, 2, 3] }
    """

    permission_classes = [IsSuperAdmin]

    def post(self, request):
        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "ids 목록이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        updated = CommonCode.objects.filter(pk__in=ids).update(is_active=False)
        return Response({"updated": updated})
