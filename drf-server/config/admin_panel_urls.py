"""
config/admin_panel_urls.py

어드민 패널 HTML 페이지 URL 설정.
config/urls.py에서 "admin-panel/" 프리픽스로 포함된다.

필터 드롭다운에 필요한 초기 데이터(부서·직급 목록 등)를 context로 전달한다.
"""

from django.urls import path
from django.views.generic import TemplateView

from apps.accounts.models.department import Department
from apps.accounts.models.position import Position
from apps.geofence.views.admin_views import GeoFenceAdminPageView
from apps.facilities.views.map_editor import MapEditorPageView
from apps.facilities.views.gas_sensor_admin import GasSensorAdminPageView
from apps.facilities.views.power_device_admin import PowerDeviceAdminPageView
from apps.facilities.models.devices import GasSensor
from apps.facilities.models.facility import Facility


class AccountsAdminPageView(TemplateView):
    """
    사용자 관리 페이지.
    필터 드롭다운용 부서·직급 목록을 context에 포함해 전달한다.
    실제 테이블 데이터는 JS가 /api/admin/accounts/ 를 fetch해서 렌더링한다.
    """

    template_name = "admin_panel/accounts/accounts_main.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "account"
        ctx["departments"] = Department.objects.filter(is_active=True).values(
            "id", "name"
        )
        ctx["positions"] = Position.objects.filter(is_active=True).values("id", "name")
        ctx["facilities"] = (
            Facility.objects.filter(is_active=True).order_by("id").values("id", "name")
        )
        return ctx


class OrganizationsAdminPageView(TemplateView):
    """
    조직 관리 페이지.
    실제 데이터는 JS가 API를 fetch해서 렌더링한다.
    """

    template_name = "admin_panel/organizations/organizations_main.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "org"
        return ctx


class PowerDataAdminPageView(TemplateView):
    """
    스마트 전력 시스템 데이터 관리 페이지.
    실제 테이블 데이터는 JS가 /api/admin/power-data/ 를 fetch해서 렌더링한다.
    장비 드롭다운은 JS가 /api/admin/power-data/devices/ 를 호출해 동적으로 채운다.
    """

    template_name = "admin_panel/data/power_data.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "power_data"
        return ctx


class GasDataAdminPageView(TemplateView):
    """
    유해가스 센서 데이터 관리 페이지.
    센서 드롭다운용 활성 센서 목록을 context로 전달한다.
    실제 테이블 데이터는 JS가 /api/admin/gas-data/ 를 fetch해서 렌더링한다.
    """

    template_name = "admin_panel/data/gas_data.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "data"
        ctx["sensors"] = (
            GasSensor.objects.filter(is_active=True)
            .values("id", "device_name")
            .order_by("device_name")
        )
        return ctx


class SafetyChecklistAdminPageView(TemplateView):
    """
    작업 전 안전 점검 체크리스트 관리 페이지.
    좌측 섹션 리스트, 우측 선택 섹션 편집, 상단 [반영 이력]/[반영 저장]을 노출한다.
    실제 데이터는 JS가 /api/admin/safety/ 엔드포인트를 fetch해 렌더링한다.
    """

    template_name = "admin_panel/safety/checklist_main.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "policy"
        return ctx


urlpatterns = [
    path(
        "accounts-management/",
        AccountsAdminPageView.as_view(),
        name="admin-accounts-page",
    ),
    path(
        "organizations/",
        OrganizationsAdminPageView.as_view(),
        name="admin-organizations-page",
    ),
    path(
        "geofence/",
        GeoFenceAdminPageView.as_view(),
        name="admin-geofence-page",
    ),
    path(
        "map-editor/",
        MapEditorPageView.as_view(),
        name="admin-map-editor",
    ),
    path(
        "facility/",
        PowerDeviceAdminPageView.as_view(),
    ),
    path(
        "gas-sensors/",
        GasSensorAdminPageView.as_view(),
        name="admin-gas-sensor",
    ),
    path(
        "data/gas/",
        GasDataAdminPageView.as_view(),
        name="admin-gas-data",
    ),
    path(
        "data/power/",
        PowerDataAdminPageView.as_view(),
        name="admin-power-data",
    ),
    path(
        "safety/checklist/",
        SafetyChecklistAdminPageView.as_view(),
        name="admin-safety-checklist-page",
    ),
]
