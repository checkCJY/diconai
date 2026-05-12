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


class NoticesAdminPageView(TemplateView):
    template_name = "admin_panel/notices/notices_main.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "notice"
        return ctx

class NoticeDetailPageView(TemplateView):
    template_name = "admin_panel/notices/notice_detail.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "notice"
        ctx["notice_id"] = kwargs["pk"]
        return ctx

class NoticeCreatePageView(TemplateView):
    template_name = "admin_panel/notices/notice_form.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "notice"
        ctx["form_mode"] = "공지사항 등록"
        ctx["form_mode_key"] = "create"
        ctx["is_edit"] = False
        return ctx

class NoticeEditPageView(TemplateView):
    template_name = "admin_panel/notices/notice_form.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "notice"
        ctx["form_mode"] = "공지사항 수정"
        ctx["form_mode_key"] = "edit"
        ctx["is_edit"] = True
        ctx["notice_id"] = kwargs["pk"]
        return ctx


class SystemLogPageView(TemplateView):
    template_name = "admin_panel/logs/system_log.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "system_log"
        return ctx

class ActivityLogPageView(TemplateView):
    template_name = "admin_panel/logs/activity_log.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "activity_log"
        return ctx

class IntegrationLogPageView(TemplateView):
    template_name = "admin_panel/logs/integration_log.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "integration_log"
        return ctx

class MapEditLogPageView(TemplateView):
    template_name = "admin_panel/logs/map_edit_log.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "map_edit_log"
        return ctx


urlpatterns = [
    path("logs/system/",        SystemLogPageView.as_view(),       name="admin-log-system"),
    path("logs/activity/",      ActivityLogPageView.as_view(),     name="admin-log-activity"),
    path("logs/integration/",   IntegrationLogPageView.as_view(),  name="admin-log-integration"),
    path("logs/map-edit/",      MapEditLogPageView.as_view(),      name="admin-log-map-edit"),
    path("notices/",                    NoticesAdminPageView.as_view(),     name="admin-notices-page"),
    path("notices/create/",             NoticeCreatePageView.as_view(),     name="admin-notice-create"),
    path("notices/<int:pk>/",           NoticeDetailPageView.as_view(),     name="admin-notice-detail"),
    path("notices/<int:pk>/edit/",      NoticeEditPageView.as_view(),       name="admin-notice-edit"),
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
]
