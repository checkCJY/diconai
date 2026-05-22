"""어드민 패널 — 알림 정책 관리 화면용 읽기 전용 selector.

검색·필터·정렬 정책의 단일 출처. view 에서 직접 ORM 호출하지 않고 본 함수만 사용.
"""

from apps.alerts.models import AlertPolicy

# 정렬 화이트리스트 — 외부 입력 검증 + 운영자가 화면에서 선택 가능한 8종.
_SORT_MAP = {
    "updated_desc": "-updated_at",
    "updated_asc": "updated_at",
    "name_asc": "name",
    "name_desc": "-name",
    "event_asc": "event_type",
    "event_desc": "-event_type",
    "active_first": "-is_active",
    "inactive_first": "is_active",
}
DEFAULT_SORT = "updated_desc"


def list_admin_policies(
    *,
    name: str = "",
    event_type: str | None = None,
    is_active: bool | None = None,
    sort: str = DEFAULT_SORT,
):
    """어드민 패널의 알림 정책 목록 쿼리셋.

    Args:
        name: 정책명 부분 검색 (icontains)
        event_type: AlarmType 필터 (예: gas_threshold)
        is_active: True/False 필터 (None 이면 전체)
        sort: _SORT_MAP 키

    Returns:
        QuerySet[AlertPolicy] — view 에서 그대로 페이지네이터에 넘김
    """
    qs = AlertPolicy.objects.select_related("target_facility").all()

    name = (name or "").strip()
    if name:
        qs = qs.filter(name__icontains=name)

    if event_type:
        qs = qs.filter(event_type=event_type)

    if is_active is not None:
        qs = qs.filter(is_active=is_active)

    return qs.order_by(_SORT_MAP.get(sort, _SORT_MAP[DEFAULT_SORT]))
