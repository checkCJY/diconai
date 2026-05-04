"""
스마트 전력 장비 관리 어드민 API.

URL 프리픽스: /api/admin/power-devices/
권한: 모든 엔드포인트 IsSuperAdmin (HTML 페이지는 admin_panel_urls.py의 TemplateView).
"""

import logging
import socket as _socket

from django.db import transaction
from django.utils import timezone
from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models.user import CustomUser
from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdmin
from apps.facilities.models import PowerDevice, PowerDeviceInspection
from apps.facilities.selectors.admin_devices import list_admin_power_devices
from apps.facilities.serializers.power_device_admin import (
    PowerDeviceAdminListSerializer,
    PowerDeviceAdminWriteSerializer,
    PowerDeviceActionWriteSerializer,
    PowerDeviceInspectionSerializer,
    PowerDeviceInspectionWriteSerializer,
)

logger = logging.getLogger(__name__)


class PowerDeviceAdminPageView(TemplateView):
    """전력 장비 관리 페이지 — HTML 셸만 반환. 데이터는 JS가 API 호출."""

    template_name = "admin_panel/power_system/power_system.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "power_system"
        return ctx


# ── 장비 코드 목록 (필터 드롭다운용) ──────────────────────────
class PowerDeviceCodesView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        codes = (
            PowerDevice.objects.filter(device_code__isnull=False)
            .exclude(device_code="")
            .order_by("device_code")
            .values_list("device_code", flat=True)
        )
        power_ids = [f"PWR-{c}" for c in codes]
        return Response(power_ids)


# ── 다음 장비 코드 ─────────────────────────────────────────────
class PowerDeviceNextCodeView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        existing = PowerDevice.objects.filter(device_code__regex=r"^\d+$").values_list(
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
class PowerDeviceConnectionCheckView(APIView):
    permission_classes = [IsSuperAdmin]

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
            logger.warning(f"[power_device_conn] ip={ip} port={port} error={exc}")
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


# ── 장치 목록 / 등록 ──────────────────────────────────────────
class PowerDeviceAdminListView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        qs = list_admin_power_devices(
            q=request.query_params.get("q", ""),
            is_active=request.query_params.get("is_active", ""),
            connection=request.query_params.get("connection", ""),
            sort=request.query_params.get("order", "device_id_asc"),
        )
        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = PowerDeviceAdminListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @transaction.atomic
    def post(self, request):
        serializer = PowerDeviceAdminWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        device = serializer.save()
        out = PowerDevice.objects.select_related(
            "facility", "department", "manager"
        ).get(pk=device.pk)
        return Response(
            PowerDeviceAdminListSerializer(out).data, status=status.HTTP_201_CREATED
        )


# ── 장치 상세 / 수정 / 비활성화 ──────────────────────────────
class PowerDeviceAdminDetailView(APIView):
    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        try:
            return PowerDevice.objects.select_related(
                "facility", "department", "manager"
            ).get(pk=pk)
        except PowerDevice.DoesNotExist:
            return None

    def get(self, request, pk):
        device = self._get(pk)
        if device is None:
            return Response(
                {"detail": "장치를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(PowerDeviceAdminListSerializer(device).data)

    @transaction.atomic
    def put(self, request, pk):
        device = self._get(pk)
        if device is None:
            return Response(
                {"detail": "장치를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = PowerDeviceAdminWriteSerializer(
            device, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(PowerDeviceAdminListSerializer(self._get(pk)).data)

    def delete(self, request, pk):
        device = self._get(pk)
        if device is None:
            return Response(
                {"detail": "장치를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        device.deactivate()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 일괄 비활성화 ─────────────────────────────────────────────
class PowerDeviceAdminBulkDeleteView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "ids 목록이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )
        count = PowerDevice.objects.filter(id__in=ids, is_active=True).update(
            is_active=False,
            deactivated_at=timezone.now(),
            status=PowerDevice.Status.INACTIVE,
        )
        return Response({"deleted": count})


# ── 점검 이력 조회 / 등록 ─────────────────────────────────────
class PowerDeviceInspectionListView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request, device_pk):
        inspections = (
            PowerDeviceInspection.objects.filter(device_id=device_pk)
            .select_related("inspector", "action_user")
            .order_by("-inspection_date", "-created_at")
        )
        return Response(PowerDeviceInspectionSerializer(inspections, many=True).data)

    def post(self, request, device_pk):
        data = request.data.copy()
        data["device"] = device_pk
        if not data.get("inspection_date"):
            data["inspection_date"] = timezone.localdate().isoformat()
        serializer = PowerDeviceInspectionWriteSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        inspection = serializer.save()
        return Response(
            PowerDeviceInspectionSerializer(inspection).data,
            status=status.HTTP_201_CREATED,
        )


# ── 조치 등록 ─────────────────────────────────────────────────
class PowerDeviceInspectionActionView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request, inspection_pk):
        try:
            inspection = PowerDeviceInspection.objects.select_related(
                "inspector", "action_user"
            ).get(pk=inspection_pk)
        except PowerDeviceInspection.DoesNotExist:
            return Response(
                {"detail": "점검 이력을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if inspection.is_actioned:
            return Response(
                {"detail": "이미 조치 완료된 점검입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PowerDeviceActionWriteSerializer(data=request.data)
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
        return Response(PowerDeviceInspectionSerializer(inspection).data)
