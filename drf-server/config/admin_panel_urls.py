"""
config/admin_panel_urls.py

어드민 패널 HTML 페이지 URL 설정. `config/urls.py`에서 `admin-panel/` 프리픽스로
include 된다.

[공통 패턴]
모든 페이지 View는 `TemplateView`를 상속해 다음 3가지만 책임진다:
1) `template_name` — `templates/admin_panel/.../*.html`
2) `active_nav` — 사이드바 활성 표시 토큰 (예: "account", "policy")
3) (선택) 필터 드롭다운 초기 데이터 context — 부서/직급/공장 같은 비변동 메타

실제 테이블/트리/CRUD 데이터는 JS가 페이지 로드 후 `/api/admin/...`을 fetch해서
렌더링한다 — 본 모듈은 페이지 셸만 제공.

[권한]
TemplateView 자체에는 권한 가드를 두지 않음 (기존 어드민 페이지 패턴 유지).
실제 권한 강제는 JS가 호출하는 API 단(`IsSuperAdminOrFacilityAdmin` 등)에서 수행.
"""

from django.urls import path
from django.views.generic import TemplateView

from apps.accounts.models.department import Department
from apps.accounts.models.position import Position
from apps.core.constants import AlarmType, EventStatus
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


class DataRetentionPolicyAdminPageView(TemplateView):
    """
    데이터 보관 정책 관리 페이지.
    실제 데이터는 JS가 /api/admin/retention-policies/ 를 fetch해서 렌더링한다.
    """

    template_name = "admin_panel/data/retention_policy.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "retention_policy"
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


class VRTrainingAdminPageView(TemplateView):
    """
    VR 교육 관리 페이지 — facility별 단일 콘텐츠 조회/교체.
    super_admin은 facility 드롭다운으로 다른 공장 콘텐츠도 조회 가능
    (사용자 관리 어드민의 facility 드롭다운과 동일 패턴).
    실제 데이터는 JS가 /api/admin/training/ 엔드포인트를 fetch해 렌더링한다.
    """

    template_name = "admin_panel/safety/vr_training_main.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "vr_training"
        ctx["facilities"] = (
            Facility.objects.filter(is_active=True).order_by("id").values("id", "name")
        )


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


class CommonCodesAdminPageView(TemplateView):
    """공통 코드 관리 페이지.

    왼쪽: CodeGroup 목록 / 오른쪽: 선택 그룹의 CommonCode 목록.
    실제 데이터는 JS 가 /api/admin/code-groups/ 를 fetch 해서 렌더링한다.
    Phase 1: 공통코드 페이지 내 CRUD만 동작 / 다른 페이지 연동은 Phase 2.
    """

    template_name = "admin_panel/common_codes/common_codes.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "common_code"
        # 모달의 수정자(readonly) 필드에 표시할 현재 로그인 사용자 이름
        # AnonymousUser 는 get_full_name() 이 없으므로 hasattr 로 방어
        user = self.request.user
        full_name = getattr(user, 'get_full_name', lambda: '')()
        ctx["current_user_display"] = full_name or getattr(user, 'username', '')
        return ctx


class ThresholdAdminPageView(TemplateView):
    """임계치 기준 관리 페이지.

    왼쪽: ThresholdGroup 목록 / 오른쪽: 선택 그룹의 Threshold 목록.
    실제 데이터는 JS 가 /api/admin/threshold-groups/ 를 fetch 해서 렌더링한다.
    """

    template_name = "admin_panel/thresholds/thresholds.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "threshold"
        return ctx


class RiskStandardsAdminPageView(TemplateView):
    """위험 기준 관리 페이지.

    RiskLevelStandard 3개 레코드 조회·수정 전용.
    필터 드롭다운용 색상 옵션을 context 로 전달.
    실제 데이터는 JS 가 /api/admin/risk-standards/ 를 fetch 해서 렌더링한다.
    """

    template_name = "admin_panel/risk_standards/risk_standards.html"

    def get_context_data(self, **kwargs):
        from apps.core.models.risk_level_standard import RiskLevelStandard

        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "risk_standard"
        # 알림강도 드롭다운 선택지
        ctx["alert_intensities"] = [
            {"value": v, "label": l}
            for v, l in RiskLevelStandard.AlertIntensity.choices
        ]
        return ctx


class EventHistoryAdminPageView(TemplateView):
    """이벤트 이력 조회 페이지.

    읽기 전용 조회 페이지 — CRUD 없음.
    필터 드롭다운용 alarm_types / event_statuses 를 context 로 전달.
    실제 데이터는 JS 가 /api/admin/alerts/events/ 를 fetch 해서 렌더링한다.
    """

    template_name = "admin_panel/events/event_history.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "event_history"
        # 이벤트 구분 드롭다운 — AlarmType choices 전달
        ctx["alarm_types"] = [
            {"value": v, "label": l} for v, l in AlarmType.choices
        ]
        # 이벤트 상태 드롭다운 — EventStatus choices 전달
        ctx["event_statuses"] = [
            {"value": v, "label": l} for v, l in EventStatus.choices
        ]
        return ctx


class AlertPolicyAdminPageView(TemplateView):
    """알림 정책 관리 페이지.

    필터 드롭다운용 AlarmType choices 를 context 로 전달. 실제 정책 데이터는 JS 가
    /api/admin/alerts/policies/ 를 fetch.
    """

    template_name = "admin_panel/alerts/policies_main.html"

    def get_context_data(self, **kwargs):
        from apps.core.constants import AlarmType

        ctx = super().get_context_data(**kwargs)
        ctx["active_nav"] = "alert_policy"
        ctx["alarm_types"] = [
            {"value": value, "label": label} for value, label in AlarmType.choices
        ]
        return ctx


urlpatterns = [
    path("logs/system/", SystemLogPageView.as_view(), name="admin-log-system"),
    path("logs/activity/", ActivityLogPageView.as_view(), name="admin-log-activity"),
    path(
        "logs/integration/",
        IntegrationLogPageView.as_view(),
        name="admin-log-integration",
    ),
    path("logs/map-edit/", MapEditLogPageView.as_view(), name="admin-log-map-edit"),
    path("notices/", NoticesAdminPageView.as_view(), name="admin-notices-page"),
    path("notices/create/", NoticeCreatePageView.as_view(), name="admin-notice-create"),
    path(
        "notices/<int:pk>/", NoticeDetailPageView.as_view(), name="admin-notice-detail"
    ),
    path(
        "notices/<int:pk>/edit/", NoticeEditPageView.as_view(), name="admin-notice-edit"
    ),
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
        "data/retention-policy/",
        DataRetentionPolicyAdminPageView.as_view(),
        name="admin-retention-policy",
    ),
    path(
        "safety/checklist/",
        SafetyChecklistAdminPageView.as_view(),
        name="admin-safety-checklist-page",
    ),
    path(
        "safety/vr-training/",
        VRTrainingAdminPageView.as_view(),
        name="admin-vr-training-page",
    ),
    path(
        "alerts/policies/",
        AlertPolicyAdminPageView.as_view(),
        name="admin-alert-policies-page",
    ),
    path(
        "events/history/",
        EventHistoryAdminPageView.as_view(),
        name="admin-event-history-page",
    ),
    path(
        "risk-standards/",
        RiskStandardsAdminPageView.as_view(),
        name="admin-risk-standards-page",
    ),
    path(
        "thresholds/",
        ThresholdAdminPageView.as_view(),
        name="admin-thresholds-page",
    ),
    path(
        "common-codes/",
        CommonCodesAdminPageView.as_view(),
        name="admin-common-codes-page",
    ),
]
