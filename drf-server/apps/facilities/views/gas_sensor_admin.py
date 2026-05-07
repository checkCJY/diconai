"""
유해가스 센서 관리 어드민 API.

URL 프리픽스: /api/admin/gas-sensors/
권한: 모든 엔드포인트 IsSuperAdmin (HTML 페이지는 admin_panel_urls.py의 TemplateView).
"""

import logging
import socket as _socket

from django.db import transaction
from django.utils import timezone
from django.views.generic import TemplateView
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models.department import Department
from apps.accounts.models.user import CustomUser
from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdmin
from apps.facilities.models import GasSensor, GasSensorInspection
from apps.facilities.selectors.admin_devices import list_admin_gas_sensors
from apps.facilities.serializers.gas_sensor_admin import (
    GasSensorAdminListSerializer,
    GasSensorAdminWriteSerializer,
    GasSensorActionWriteSerializer,
    GasSensorInspectionSerializer,
    GasSensorInspectionWriteSerializer,
)

logger = logging.getLogger(__name__)


class GasSensorAdminPageView(TemplateView):
    """가스 센서 관리 페이지 — HTML 셸만 반환. 데이터는 JS가 API 호출.

    페이지 진입은 비인증 허용(JS가 토큰 없으면 로그인으로 리다이렉트).
    실제 데이터 API는 IsSuperAdmin로 보호된다.
    """

    template_name = "admin_panel/gas_sensor/gas_sensor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "gas_sensor"
        return ctx


# ── 드롭다운 옵션 ─────────────────────────────────────────────
class DepartmentSelectView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Dropdowns"],
        summary="부서 드롭다운 옵션",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="DepartmentSelectItem",
                fields={
                    "id": serializers.IntegerField(),
                    "name": serializers.CharField(),
                },
                many=True,
            ),
        },
    )
    def get(self, request):
        depts = Department.objects.filter(is_active=True).values("id", "name")
        return Response(list(depts))


class ManagerSelectView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Dropdowns"],
        summary="담당자 드롭다운 옵션",
        description="부서 선택 시(`department_id`) 해당 부서 소속만 필터링.",
        parameters=[OpenApiParameter(name="department_id", type=int, required=False)],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="ManagerSelectItem",
                fields={
                    "id": serializers.IntegerField(),
                    "name": serializers.CharField(),
                    "username": serializers.CharField(),
                },
                many=True,
            ),
        },
    )
    def get(self, request):
        dept_id = request.query_params.get("department_id")
        qs = CustomUser.objects.filter(is_active=True)
        if dept_id:
            qs = qs.filter(dept_memberships__department_id=dept_id)
        data = [
            {
                "id": u.id,
                "name": u.get_full_name().strip() or u.username,
                "username": u.username,
            }
            for u in qs
        ]
        return Response(data)


# ── 다음 장비 코드 ─────────────────────────────────────────────
class GasSensorNextCodeView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="다음 가용 가스 센서 코드 조회",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="GasSensorNextCode",
                fields={"code": serializers.CharField()},
            ),
        },
    )
    def get(self, request):
        existing = GasSensor.objects.filter(device_code__regex=r"^\d+$").values_list(
            "device_code", flat=True
        )
        codes = set()
        for c in existing:
            try:
                codes.add(int(c))
            except ValueError:
                pass
        next_num = 1
        while next_num in codes:
            next_num += 1
        return Response({"code": f"{next_num:03d}"})


# ── 연결 확인 ─────────────────────────────────────────────────
class GasSensorConnectionCheckView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="가스 센서 통신 연결 확인 (TCP)",
        request=inline_serializer(
            name="GasSensorConnectionCheckRequest",
            fields={
                "ip_address": serializers.IPAddressField(),
                "port": serializers.IntegerField(min_value=1, max_value=65535),
            },
        ),
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="GasSensorConnectionCheckResponse",
                fields={
                    "ok": serializers.BooleanField(),
                    "checked_at": serializers.DateTimeField(),
                    "detail": serializers.CharField(required=False),
                },
            ),
            400: OpenApiResponse(description="IP/Port 검증 실패"),
        },
    )
    def post(self, request):
        ip = request.data.get("ip_address", "").strip()
        port = request.data.get("port")

        if not ip:
            return Response(
                {"detail": "IP 주소를 입력해 주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not port:
            return Response(
                {"detail": "포트 번호를 입력해 주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            port = int(port)
            if not (1 <= port <= 65535):
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {"detail": "포트 번호는 1~65535 범위로 입력해 주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((ip, port))
            sock.close()
            ok = result == 0
        except OSError as exc:
            logger.warning(f"[gas_sensor_conn] ip={ip} port={port} error={exc}")
            ok = False

        checked_at = timezone.now()
        if not ok:
            return Response(
                {
                    "ok": False,
                    "checked_at": checked_at,
                    "detail": "장비와 연결할 수 없습니다. 통신 정보를 확인해 주세요.",
                }
            )
        return Response({"ok": True, "checked_at": checked_at})


# ── 센서 목록 / 등록 ──────────────────────────────────────────
class GasSensorAdminListView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="가스 센서 목록 (페이지네이션)",
        parameters=[
            OpenApiParameter(
                name="q", type=str, required=False, description="이름/코드 검색"
            ),
            OpenApiParameter(name="is_active", type=str, required=False),
            OpenApiParameter(name="connection", type=str, required=False),
            OpenApiParameter(name="order", type=str, required=False),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: GasSensorAdminListSerializer(many=True),
        },
    )
    def get(self, request):
        qs = list_admin_gas_sensors(
            q=request.query_params.get("q", ""),
            is_active=request.query_params.get("is_active", ""),
            connection=request.query_params.get("connection", ""),
            sort=request.query_params.get("order", "sensor_id_asc"),
        )
        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = GasSensorAdminListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="가스 센서 신규 등록",
        request=GasSensorAdminWriteSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            201: GasSensorAdminListSerializer,
            400: OpenApiResponse(description="검증 실패"),
        },
    )
    @transaction.atomic
    def post(self, request):
        serializer = GasSensorAdminWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        sensor = serializer.save()
        out = GasSensor.objects.select_related("facility", "department", "manager").get(
            pk=sensor.pk
        )
        return Response(
            GasSensorAdminListSerializer(out).data, status=status.HTTP_201_CREATED
        )


# ── 센서 상세 / 수정 / 비활성화 ──────────────────────────────
class GasSensorAdminDetailView(APIView):
    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        try:
            return GasSensor.objects.select_related(
                "facility", "department", "manager"
            ).get(pk=pk)
        except GasSensor.DoesNotExist:
            return None

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="가스 센서 상세 조회",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: GasSensorAdminListSerializer,
            404: OpenApiResponse(description="센서 없음"),
        },
    )
    def get(self, request, pk):
        sensor = self._get(pk)
        if sensor is None:
            return Response(
                {"detail": "센서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(GasSensorAdminListSerializer(sensor).data)

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="가스 센서 수정 (Partial)",
        request=GasSensorAdminWriteSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: GasSensorAdminListSerializer,
            400: OpenApiResponse(description="검증 실패"),
            404: OpenApiResponse(description="센서 없음"),
        },
    )
    @transaction.atomic
    def put(self, request, pk):
        sensor = self._get(pk)
        if sensor is None:
            return Response(
                {"detail": "센서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = GasSensorAdminWriteSerializer(
            sensor, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(GasSensorAdminListSerializer(self._get(pk)).data)

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="가스 센서 비활성화 (Soft Delete)",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            204: OpenApiResponse(description="삭제 완료"),
            404: OpenApiResponse(description="센서 없음"),
        },
    )
    def delete(self, request, pk):
        sensor = self._get(pk)
        if sensor is None:
            return Response(
                {"detail": "센서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        sensor.deactivate()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 일괄 비활성화 ─────────────────────────────────────────────
class GasSensorAdminBulkDeleteView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="가스 센서 일괄 비활성화",
        request=inline_serializer(
            name="GasSensorBulkDeleteRequest",
            fields={"ids": serializers.ListField(child=serializers.IntegerField())},
        ),
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="GasSensorBulkDeleteResponse",
                fields={"deleted": serializers.IntegerField()},
            ),
            400: OpenApiResponse(description="ids 누락"),
        },
    )
    def post(self, request):
        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "ids 목록이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )
        now = timezone.now()
        count = GasSensor.objects.filter(id__in=ids, is_active=True).update(
            is_active=False, deactivated_at=now, status=GasSensor.Status.INACTIVE
        )
        return Response({"deleted": count})


# ── 점검 이력 조회 / 점검 등록 ──────────────────────────────
class GasSensorInspectionListView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="가스 센서 점검 이력 목록",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: GasSensorInspectionSerializer(many=True),
        },
    )
    def get(self, request, sensor_pk):
        inspections = (
            GasSensorInspection.objects.filter(sensor_id=sensor_pk)
            .select_related("inspector", "action_user")
            .order_by("-inspection_date", "-created_at")
        )
        return Response(GasSensorInspectionSerializer(inspections, many=True).data)

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="가스 센서 점검 이력 등록",
        request=GasSensorInspectionWriteSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            201: GasSensorInspectionSerializer,
            400: OpenApiResponse(description="검증 실패"),
        },
    )
    def post(self, request, sensor_pk):
        data = request.data.copy()
        data["sensor"] = sensor_pk
        if not data.get("inspection_date"):
            data["inspection_date"] = timezone.localdate().isoformat()
        serializer = GasSensorInspectionWriteSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        inspection = serializer.save()
        return Response(
            GasSensorInspectionSerializer(inspection).data,
            status=status.HTTP_201_CREATED,
        )


# ── 조치 등록 ─────────────────────────────────────────────────
class GasSensorInspectionActionView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Gas Sensor"],
        summary="가스 센서 점검에 대한 조치 등록",
        request=GasSensorActionWriteSerializer,
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: GasSensorInspectionSerializer,
            400: OpenApiResponse(description="이미 조치 완료 / 검증 실패"),
            404: OpenApiResponse(description="점검 이력 없음"),
        },
    )
    def post(self, request, inspection_pk):
        try:
            inspection = GasSensorInspection.objects.select_related(
                "inspector", "action_user"
            ).get(pk=inspection_pk)
        except GasSensorInspection.DoesNotExist:
            return Response(
                {"detail": "점검 이력을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if inspection.is_actioned:
            return Response(
                {"detail": "이미 조치 완료된 점검입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GasSensorActionWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        inspection.is_actioned = True
        inspection.action_date = timezone.localdate()
        inspection.action_notes = serializer.validated_data["action_notes"]
        action_user_id = serializer.validated_data.get("action_user")
        if action_user_id:
            try:
                inspection.action_user = CustomUser.objects.get(pk=action_user_id)
            except CustomUser.DoesNotExist:
                pass
        inspection.save(
            update_fields=[
                "is_actioned",
                "action_date",
                "action_notes",
                "action_user",
                "updated_at",
            ]
        )
        return Response(GasSensorInspectionSerializer(inspection).data)
