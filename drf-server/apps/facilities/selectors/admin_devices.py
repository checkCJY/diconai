"""어드민 패널 — 가스 센서·전력 장비 관리 화면용 읽기 전용 selector.

gas_sensor_admin.py / power_device_admin.py의 List view에서 호출하던
검색·필터·정렬 로직을 한 곳에 모은다. 외부 입력은 화이트리스트로 검증한다.
"""

from django.db.models import Case, IntegerField, When

from apps.facilities.models import GasSensor, PowerDevice


# 정렬 화이트리스트 — 가스/전력 공용 (필드명 동일).
_DEVICE_SORT_MAP = {
    "sensor_id_asc": "device_code",
    "sensor_id_desc": "-device_code",
    "device_id_asc": "device_code",
    "device_id_desc": "-device_code",
    "last_reading_desc": "-last_reading",
    "last_reading_asc": "last_reading",
    "inspection_desc": "-inspections__inspection_date",
    "inspection_asc": "inspections__inspection_date",
}


def _apply_common_filters(qs, *, q, code_prefix, is_active, connection):
    """device_code 검색·사용여부·연결상태 공통 필터.

    code_prefix: "GAS-" 또는 "PWR-" — 앞에 붙은 prefix를 떼고 device_code로 검색.
    """
    q = (q or "").strip()
    if q:
        if q.upper().startswith(code_prefix):
            qs = qs.filter(device_code=q[len(code_prefix) :])
        else:
            qs = qs.filter(device_name__icontains=q)

    is_active = (is_active or "").strip()
    if is_active == "true":
        qs = qs.filter(is_active=True)
    elif is_active == "false":
        qs = qs.filter(is_active=False)

    conn = (connection or "").strip()
    if conn == "normal":
        qs = qs.filter(is_active=True).exclude(status__in=["offline", "error"])
    elif conn == "disconnected":
        qs = qs.filter(status__in=["offline", "error"])
    elif conn == "inactive":
        qs = qs.filter(is_active=False)

    return qs


def _apply_priority_order(qs, sort, default_field="device_code"):
    """이상 상태(offline/error) 센서를 최상단으로 우선 정렬.

    selector 호출자가 결정한 selected_sort 보조 정렬을 두 번째 키로 사용.
    """
    order_field = _DEVICE_SORT_MAP.get(sort or "", default_field)
    return (
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


def list_admin_gas_sensors(*, q="", is_active="", connection="", sort="sensor_id_asc"):
    qs = GasSensor.objects.select_related(
        "facility", "department", "manager"
    ).prefetch_related("inspections")
    qs = _apply_common_filters(
        qs, q=q, code_prefix="GAS-", is_active=is_active, connection=connection
    )
    return _apply_priority_order(qs, sort)


def list_admin_power_devices(
    *, q="", is_active="", connection="", sort="device_id_asc"
):
    qs = PowerDevice.objects.select_related(
        "facility", "department", "manager"
    ).prefetch_related("inspections")
    qs = _apply_common_filters(
        qs, q=q, code_prefix="PWR-", is_active=is_active, connection=connection
    )
    return _apply_priority_order(qs, sort)
