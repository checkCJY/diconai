"""
apps/monitoring/admin_urls.py

유해가스 데이터 관리 어드민 API URL.
config/urls.py에서 "api/admin/" 프리픽스로 포함된다.
→ 실제 접근 경로: /api/admin/gas-data/, /api/admin/gas-data/export/, /api/admin/gas-data/sensors/
"""

from django.urls import path

from apps.monitoring.views.gas_data_admin import (
    GasDataAdminListView,
    GasDataAdminExportView,
    GasDataAdminSensorListView,
)
from apps.monitoring.views.power_data_admin import (
    PowerDataAdminListView,
    PowerDataAdminExportView,
    PowerDataAdminDeviceListView,
)

urlpatterns = [
    # 목록 조회 (필터 + 페이지네이션)
    path("gas-data/", GasDataAdminListView.as_view(), name="admin-gas-data-list"),
    # CSV 전체 내보내기 (동일 필터, 페이지네이션 없음)
    path("gas-data/export/", GasDataAdminExportView.as_view(), name="admin-gas-data-export"),
    # 센서 드롭다운용 활성 센서 목록
    path("gas-data/sensors/", GasDataAdminSensorListView.as_view(), name="admin-gas-data-sensors"),

    # 전력 데이터 목록 조회 (필터 + 페이지네이션)
    path("power-data/", PowerDataAdminListView.as_view(), name="admin-power-data-list"),
    # CSV 전체 내보내기 (동일 필터, 페이지네이션 없음)
    path("power-data/export/", PowerDataAdminExportView.as_view(), name="admin-power-data-export"),
    # 장비 드롭다운용 활성 전력 장비 목록
    path("power-data/devices/", PowerDataAdminDeviceListView.as_view(), name="admin-power-data-devices"),
]
