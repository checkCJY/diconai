from django.urls import path
from apps.facilities.views.map_editor import MapEditorObjectsView, MapEditorSaveView
from apps.facilities.views.power_device_admin import (
    PowerDeviceAdminListView,
    PowerDeviceAdminDetailView,
    PowerDeviceAdminBulkDeleteView,
    PowerDeviceCodesView,
    PowerDeviceNextCodeView,
    PowerDeviceConnectionCheckView,
    PowerDeviceInspectionListView,
    PowerDeviceInspectionActionView,
)
from apps.facilities.views.gas_sensor_admin import (
    DepartmentSelectView,
    ManagerSelectView,
    GasSensorNextCodeView,
    GasSensorConnectionCheckView,
    GasSensorAdminListView,
    GasSensorAdminDetailView,
    GasSensorAdminBulkDeleteView,
    GasSensorInspectionListView,
    GasSensorInspectionActionView,
)
from apps.facilities.views.facility_admin import (
    FacilityAdminListView,
    FacilityAdminDetailView,
    FacilityAdminBulkDeleteView,
    FacilityPowerDeviceOptionsView,
    FacilitySelectView,
    PowerDeviceSelectView,
    EquipmentAdminListView,
    EquipmentAdminDetailView,
    EquipmentAdminBulkDeleteView,
    PowerDeviceAdminListView as LegacyPowerDeviceListView,
    PowerDeviceAdminBulkDeleteView as LegacyPowerDeviceBulkDeleteView,
)

urlpatterns = [
    # 지도 편집
    path(
        "map-editor/objects/", MapEditorObjectsView.as_view(), name="map-editor-objects"
    ),
    path("map-editor/save/", MapEditorSaveView.as_view(), name="map-editor-save"),
    # 기존 공장 API (map-editor 내부 사용)
    path("facilities/", FacilityAdminListView.as_view(), name="facility-list"),
    path(
        "facilities/bulk-delete/",
        FacilityAdminBulkDeleteView.as_view(),
        name="facility-bulk-delete",
    ),
    path(
        "facilities/power-device-options/",
        FacilityPowerDeviceOptionsView.as_view(),
        name="facility-power-device-options",
    ),
    path("facilities/select/", FacilitySelectView.as_view(), name="facility-select"),
    path(
        "facilities/<int:pk>/",
        FacilityAdminDetailView.as_view(),
        name="facility-detail",
    ),
    # 전력 장치 선택 드롭다운 (미연결만)
    path(
        "facilities/devices/select/",
        PowerDeviceSelectView.as_view(),
        name="device-select",
    ),
    # 설비(Equipment) 관리
    path("equipments/", EquipmentAdminListView.as_view(), name="equipment-list"),
    path(
        "equipments/bulk-delete/",
        EquipmentAdminBulkDeleteView.as_view(),
        name="equipment-bulk-delete",
    ),
    path(
        "equipments/<int:pk>/",
        EquipmentAdminDetailView.as_view(),
        name="equipment-detail",
    ),
    # 유해가스 센서 관리
    path(
        "gas-sensors/next-code/",
        GasSensorNextCodeView.as_view(),
        name="gas-sensor-next-code",
    ),
    path(
        "gas-sensors/check-connection/",
        GasSensorConnectionCheckView.as_view(),
        name="gas-sensor-check-conn",
    ),
    path(
        "gas-sensors/bulk-delete/",
        GasSensorAdminBulkDeleteView.as_view(),
        name="gas-sensor-bulk-delete",
    ),
    path("gas-sensors/", GasSensorAdminListView.as_view(), name="gas-sensor-list"),
    path(
        "gas-sensors/<int:pk>/",
        GasSensorAdminDetailView.as_view(),
        name="gas-sensor-detail",
    ),
    path(
        "gas-sensors/<int:sensor_pk>/inspections/",
        GasSensorInspectionListView.as_view(),
        name="gas-sensor-inspections",
    ),
    path(
        "gas-sensors/inspections/<int:inspection_pk>/action/",
        GasSensorInspectionActionView.as_view(),
        name="gas-sensor-action",
    ),
    # 스마트 전력 시스템 관리
    path(
        "power-devices/codes/",
        PowerDeviceCodesView.as_view(),
        name="power-device-codes",
    ),
    path(
        "power-devices/next-code/",
        PowerDeviceNextCodeView.as_view(),
        name="power-device-next-code",
    ),
    path(
        "power-devices/check-connection/",
        PowerDeviceConnectionCheckView.as_view(),
        name="power-device-check-conn",
    ),
    path(
        "power-devices/bulk-delete/",
        PowerDeviceAdminBulkDeleteView.as_view(),
        name="power-device-bulk-delete",
    ),
    path(
        "power-devices/", PowerDeviceAdminListView.as_view(), name="power-device-list"
    ),
    path(
        "power-devices/<int:pk>/",
        PowerDeviceAdminDetailView.as_view(),
        name="power-device-detail",
    ),
    path(
        "power-devices/<int:device_pk>/inspections/",
        PowerDeviceInspectionListView.as_view(),
        name="power-device-inspections",
    ),
    path(
        "power-devices/inspections/<int:inspection_pk>/action/",
        PowerDeviceInspectionActionView.as_view(),
        name="power-device-action",
    ),
    # 드롭다운 옵션
    path(
        "departments/select/", DepartmentSelectView.as_view(), name="department-select"
    ),
    path("managers/select/", ManagerSelectView.as_view(), name="manager-select"),
    # 기존 PowerDevice API (하위 호환 — facility_admin 뷰 유지)
    path(
        "facilities/devices/", LegacyPowerDeviceListView.as_view(), name="device-list"
    ),
    path(
        "facilities/devices/bulk-delete/",
        LegacyPowerDeviceBulkDeleteView.as_view(),
    ),
    # 기존 PowerDevice API (하위 호환)
    path("facilities/devices/", PowerDeviceAdminListView.as_view(), name="device-list"),
    path(
        "facilities/devices/bulk-delete/",
        PowerDeviceAdminBulkDeleteView.as_view(),
        name="device-bulk-delete",
    ),
    path(
        "facilities/devices/<int:pk>/",
        PowerDeviceAdminDetailView.as_view(),
        name="device-detail",
    ),
]
