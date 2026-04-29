from django.urls import path
from apps.facilities.views.map_editor import MapEditorObjectsView, MapEditorSaveView
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
    PowerDeviceAdminListView,
    PowerDeviceAdminDetailView,
    PowerDeviceAdminBulkDeleteView,
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
