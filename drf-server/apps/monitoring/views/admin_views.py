# apps/monitoring/views/admin_views.py
# 전력·가스 데이터 관리 어드민 페이지 뷰 — 슈퍼관리자 전용.

from django.shortcuts import render
from rest_framework.views import APIView

from apps.core.permissions import IsSuperAdmin


class PowerDataAdminPageView(APIView):
    """스마트 전력 시스템 데이터 관리 페이지 — 슈퍼관리자 전용."""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        return render(
            request, "admin_panel/data/power_data.html", {"active_nav": "power_data"}
        )


class GasDataAdminPageView(APIView):
    """유해가스 센서 데이터 관리 페이지 — 슈퍼관리자 전용."""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        from apps.facilities.models.devices import GasSensor

        ctx = {
            "active_nav": "data",
            "sensors": (
                GasSensor.objects.filter(is_active=True)
                .values("id", "device_name")
                .order_by("device_name")
            ),
        }
        return render(request, "admin_panel/data/gas_data.html", ctx)
