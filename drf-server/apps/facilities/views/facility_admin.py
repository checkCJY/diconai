"""
공장(Facility)·설비(Equipment)·전력 장치(PowerDevice) 어드민 API.

URL 프리픽스: /api/admin/facilities/, /api/admin/equipments/, /api/admin/power-devices/
권한: 모든 엔드포인트 IsSuperAdmin (HTML 페이지는 admin_panel_urls.py의 TemplateView).
"""

from django.db.models import Q
from django.utils import timezone
from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdmin
from apps.facilities.models import Facility, Equipment
from apps.facilities.models.devices import PowerDevice
from apps.facilities.serializers.facility_admin import (
    FacilityAdminListSerializer,
    FacilityAdminWriteSerializer,
    FacilitySelectSerializer,
    PowerDeviceSelectSerializer,
    EquipmentAdminListSerializer,
    EquipmentAdminWriteSerializer,
    PowerDeviceAdminListSerializer,
    PowerDeviceAdminWriteSerializer,
)


class FacilityAdminPageView(TemplateView):
    """공장·설비 관리 페이지 — HTML 셸만 반환. 데이터는 JS가 API 호출."""

    template_name = "admin_panel/facility/facility.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "facility"
        return ctx


# ── 기존 공장 API (map-editor 내부 사용) ──────────────────────
class FacilityAdminListView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        qs = (
            Facility.objects.all()
            .prefetch_related("powerdevices")
            .select_related("manager")
        )
        q = request.query_params.get("q", "").strip()
        if q:
            if q.upper().startswith("FAC-"):
                try:
                    qs = qs.filter(id=int(q[4:]))
                except ValueError:
                    qs = qs.none()
            else:
                qs = qs.filter(name__icontains=q)
        power_device = request.query_params.get("power_device", "").strip()
        if power_device:
            qs = qs.filter(
                powerdevices__device_id=power_device, powerdevices__is_active=True
            )
        is_active = request.query_params.get("is_active", "").strip()
        if is_active == "true":
            qs = qs.filter(is_active=True)
        elif is_active == "false":
            qs = qs.filter(is_active=False)
        order = request.query_params.get("order", "-created_at")
        if order not in ["id", "-id", "name", "-name", "created_at", "-created_at"]:
            order = "-created_at"
        qs = qs.order_by(order)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = FacilityAdminListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = FacilityAdminWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        facility = serializer.save()
        return Response(
            FacilityAdminListSerializer(facility).data, status=status.HTTP_201_CREATED
        )


class FacilityAdminDetailView(APIView):
    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        try:
            return Facility.objects.get(pk=pk)
        except Facility.DoesNotExist:
            return None

    def put(self, request, pk):
        facility = self._get(pk)
        if facility is None:
            return Response(
                {"detail": "공장을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = FacilityAdminWriteSerializer(
            facility, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(FacilityAdminListSerializer(facility).data)

    def delete(self, request, pk):
        facility = self._get(pk)
        if facility is None:
            return Response(
                {"detail": "공장을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        facility.deactivate()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FacilityAdminBulkDeleteView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "ids 목록이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )
        count = Facility.objects.filter(id__in=ids, is_active=True).update(
            is_active=False, deactivated_at=timezone.now()
        )
        return Response({"deleted": count})


class FacilityPowerDeviceOptionsView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        devices = PowerDevice.objects.filter(is_active=True).values(
            "id", "device_id", "device_name", "facility_id"
        )
        return Response(list(devices))


# ── 공장 선택 드롭다운 ────────────────────────────────────────
class FacilitySelectView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        facilities = Facility.objects.filter(is_active=True).order_by("id")
        return Response(FacilitySelectSerializer(facilities, many=True).data)


# ── 전력 장치 선택 드롭다운 (미연결 + 현재 설비 연결 장치) ────────
class PowerDeviceSelectView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        current_equipment_id = request.query_params.get("equipment_id")

        if current_equipment_id:
            # 수정 모드: 다른 설비에 연결되지 않은 모든 장치(활성/비활성) + 현재 설비 연결 장치
            qs = PowerDevice.objects.filter(
                Q(equipment__isnull=True) | Q(equipment__id=current_equipment_id)
            )
        else:
            # 등록 모드: 활성이고 미연결인 장치만
            qs = PowerDevice.objects.filter(is_active=True, equipment__isnull=True)

        return Response(PowerDeviceSelectSerializer(qs, many=True).data)


# ── 설비(Equipment) CRUD ──────────────────────────────────────
class EquipmentAdminListView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        qs = Equipment.objects.select_related(
            "facility", "facility__manager", "power_device"
        ).all()

        # 검색 (설비코드 EQP-XXX 또는 설비명)
        q = request.query_params.get("q", "").strip()
        if q:
            if q.upper().startswith("EQP-"):
                try:
                    qs = qs.filter(id=int(q[4:]))
                except ValueError:
                    qs = qs.none()
            else:
                qs = qs.filter(name__icontains=q)

        # 공장 필터
        facility_id = request.query_params.get("facility", "").strip()
        if facility_id:
            qs = qs.filter(facility_id=facility_id)

        # 사용여부 필터
        is_active = request.query_params.get("is_active", "").strip()
        if is_active == "true":
            qs = qs.filter(is_active=True)
        elif is_active == "false":
            qs = qs.filter(is_active=False)

        # 정렬
        order = request.query_params.get("order", "-created_at")
        if order not in ["id", "-id", "name", "-name", "created_at", "-created_at"]:
            order = "-created_at"
        qs = qs.order_by(order)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = EquipmentAdminListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = EquipmentAdminWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        equipment = serializer.save()
        out = Equipment.objects.select_related(
            "facility", "facility__manager", "power_device"
        ).get(pk=equipment.pk)
        return Response(
            EquipmentAdminListSerializer(out).data, status=status.HTTP_201_CREATED
        )


class EquipmentAdminDetailView(APIView):
    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        try:
            return Equipment.objects.select_related(
                "facility", "facility__manager", "power_device"
            ).get(pk=pk)
        except Equipment.DoesNotExist:
            return None

    def get(self, request, pk):
        equipment = self._get(pk)
        if equipment is None:
            return Response(
                {"detail": "설비를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(EquipmentAdminListSerializer(equipment).data)

    def put(self, request, pk):
        equipment = self._get(pk)
        if equipment is None:
            return Response(
                {"detail": "설비를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        was_active = equipment.is_active
        old_pd_id = equipment.power_device_id
        serializer = EquipmentAdminWriteSerializer(
            equipment, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        updated = serializer.save()

        # 활성 설비에 장치가 연결된 경우(신규 연결 포함) → 장치도 재활성화
        if updated.is_active and updated.power_device_id:
            if not was_active or updated.power_device_id != old_pd_id:
                pd = updated.power_device
                if not pd.is_active:
                    pd.is_active = True
                    pd.status = pd.Status.NORMAL
                    pd.deactivated_at = None
                    pd.save(
                        update_fields=[
                            "is_active",
                            "status",
                            "deactivated_at",
                            "updated_at",
                        ]
                    )

        out = self._get(pk)
        return Response(EquipmentAdminListSerializer(out).data)

    def delete(self, request, pk):
        equipment = self._get(pk)
        if equipment is None:
            return Response(
                {"detail": "설비를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        equipment.deactivate()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EquipmentAdminBulkDeleteView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "ids 목록이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )
        equipments = Equipment.objects.filter(
            id__in=ids, is_active=True
        ).select_related("power_device")
        count = 0
        for equipment in equipments:
            equipment.deactivate()
            count += 1
        return Response({"deleted": count})


# ── 기존 PowerDevice API (하위 호환) ──────────────────────────
class PowerDeviceAdminListView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        qs = PowerDevice.objects.select_related("facility", "facility__manager").all()
        facility_id = request.query_params.get("facility", "").strip()
        if facility_id:
            qs = qs.filter(facility_id=facility_id)
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(device_name__icontains=q) | Q(device_id__icontains=q))
        is_active = request.query_params.get("is_active", "").strip()
        if is_active == "true":
            qs = qs.filter(is_active=True)
        elif is_active == "false":
            qs = qs.filter(is_active=False)
        order = request.query_params.get("order", "-created_at")
        if order not in [
            "id",
            "-id",
            "device_name",
            "-device_name",
            "created_at",
            "-created_at",
        ]:
            order = "-created_at"
        qs = qs.order_by(order)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = PowerDeviceAdminListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = PowerDeviceAdminWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        device = serializer.save()
        out = PowerDevice.objects.select_related("facility", "facility__manager").get(
            pk=device.pk
        )
        return Response(
            PowerDeviceAdminListSerializer(out).data, status=status.HTTP_201_CREATED
        )


class PowerDeviceAdminDetailView(APIView):
    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        try:
            return PowerDevice.objects.select_related(
                "facility", "facility__manager"
            ).get(pk=pk)
        except PowerDevice.DoesNotExist:
            return None

    def get(self, request, pk):
        device = self._get(pk)
        if device is None:
            return Response(
                {"detail": "설비를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(PowerDeviceAdminListSerializer(device).data)

    def put(self, request, pk):
        device = self._get(pk)
        if device is None:
            return Response(
                {"detail": "설비를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
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
                {"detail": "설비를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        device.deactivate()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PowerDeviceAdminBulkDeleteView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "ids 목록이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )
        now = timezone.now()
        count = PowerDevice.objects.filter(id__in=ids, is_active=True).update(
            is_active=False, deactivated_at=now, status=PowerDevice.Status.INACTIVE
        )
        return Response({"deleted": count})
