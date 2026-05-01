import socket as _socket

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models.department import Department
from apps.accounts.models.user import CustomUser
from apps.facilities.models import GasSensor, GasSensorInspection
from apps.facilities.serializers.gas_sensor_admin import (
    GasSensorAdminListSerializer,
    GasSensorAdminWriteSerializer,
    GasSensorActionWriteSerializer,
    GasSensorInspectionSerializer,
    GasSensorInspectionWriteSerializer,
)


class GasSensorAdminPageView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        from django.shortcuts import render

        return render(
            request,
            "admin_panel/gas_sensor/gas_sensor.html",
            {"active_nav": "gas_sensor"},
        )


# ── 드롭다운 옵션 ─────────────────────────────────────────────
class DepartmentSelectView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        depts = Department.objects.filter(is_active=True).values("id", "name")
        return Response(list(depts))


class ManagerSelectView(APIView):
    authentication_classes = []
    permission_classes = []

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
    authentication_classes = []
    permission_classes = []

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
    authentication_classes = []
    permission_classes = []

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
        except Exception:
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
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        qs = GasSensor.objects.select_related(
            "facility", "department", "manager"
        ).prefetch_related("inspections")

        # 검색
        q = request.query_params.get("q", "").strip()
        if q:
            if q.upper().startswith("GAS-"):
                qs = qs.filter(device_code=q[4:])
            else:
                qs = qs.filter(device_name__icontains=q)

        # 사용 여부 필터
        is_active = request.query_params.get("is_active", "").strip()
        if is_active == "true":
            qs = qs.filter(is_active=True)
        elif is_active == "false":
            qs = qs.filter(is_active=False)

        # 연결 상태 필터 (직렬화 get_connection_status 로직과 동일하게 적용)
        conn = request.query_params.get("connection", "").strip()
        if conn == "normal":
            qs = qs.filter(is_active=True).exclude(status__in=["offline", "error"])
        elif conn == "disconnected":
            qs = qs.filter(status__in=["offline", "error"])
        elif conn == "inactive":
            qs = qs.filter(is_active=False)

        # 정렬 (이상 센서 최상단, 이후 선택 정렬)
        order = request.query_params.get("order", "sensor_id_asc")
        order_map = {
            "sensor_id_asc": "device_code",
            "sensor_id_desc": "-device_code",
            "last_reading_desc": "-last_reading",
            "last_reading_asc": "last_reading",
            "inspection_desc": "-inspections__inspection_date",
            "inspection_asc": "inspections__inspection_date",
        }
        order_field = order_map.get(order, "device_code")

        # 이상 상태(연결 끊김) 우선 정렬
        from django.db.models import Case, IntegerField, When

        qs = (
            qs.annotate(
                priority=Case(
                    When(status__in=["offline", "error"], then=0),
                    default=1,
                    output_field=IntegerField(),
                )
            )
            .order_by("priority", order_field)
            .distinct()
        )

        # 페이지네이션
        try:
            page = max(1, int(request.query_params.get("page", 1)))
            page_size = max(1, min(100, int(request.query_params.get("page_size", 10))))
        except (ValueError, TypeError):
            page, page_size = 1, 10

        total = qs.count()
        sensors = qs[(page - 1) * page_size : page * page_size]
        return Response(
            {
                "total": total,
                "page": page,
                "page_size": page_size,
                "results": GasSensorAdminListSerializer(sensors, many=True).data,
            }
        )

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
    authentication_classes = []
    permission_classes = []

    def _get(self, pk):
        try:
            return GasSensor.objects.select_related(
                "facility", "department", "manager"
            ).get(pk=pk)
        except GasSensor.DoesNotExist:
            return None

    def get(self, request, pk):
        sensor = self._get(pk)
        if sensor is None:
            return Response(
                {"detail": "센서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(GasSensorAdminListSerializer(sensor).data)

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
    authentication_classes = []
    permission_classes = []

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
    authentication_classes = []
    permission_classes = []

    def get(self, request, sensor_pk):
        inspections = (
            GasSensorInspection.objects.filter(sensor_id=sensor_pk)
            .select_related("inspector", "action_user")
            .order_by("-inspection_date", "-created_at")
        )
        return Response(GasSensorInspectionSerializer(inspections, many=True).data)

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
    authentication_classes = []
    permission_classes = []

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
