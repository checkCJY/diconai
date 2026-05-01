"""
config/admin_panel_urls.py

어드민 패널 HTML 페이지 URL 설정.
config/urls.py에서 "admin-panel/" 프리픽스로 포함된다.

각 페이지 뷰는 LoginRequiredMixin을 통해 미인증 접근을 차단하고,
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
        name="admin-facility",
    ),
    path(
        "gas-sensors/",
        GasSensorAdminPageView.as_view(),
        name="admin-gas-sensor",
    ),
]
