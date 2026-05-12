"""어드민 패널 — 사용자 관리 화면용 읽기 전용 selector.

view에서 직접 ORM filter/order_by를 호출하던 로직을 한곳에 모은다.
검색·필터·정렬·prefetch 정책의 단일 출처가 된다.
"""

from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# 정렬 화이트리스트 — 외부 입력을 그대로 ORM에 넘기지 않기 위함.
_SORT_MAP = {
    "name_asc": "name",
    "name_desc": "-name",
    "date_asc": "date_joined",
    "date_desc": "-date_joined",
}
DEFAULT_SORT = "name_asc"


def list_admin_users(
    *,
    name="",
    department_id=None,
    position_id=None,
    user_type=None,
    account_status=None,
    sort=DEFAULT_SORT,
):
    """
    어드민 패널의 사용자 목록 쿼리셋.

    Args:
        name: 이름 부분 검색(icontains)
        department_id: 사용자의 primary 부서 ID
        position_id: 직급 ID
        user_type: super_admin/facility_admin/worker/viewer
        account_status: active/locked/inactive
        sort: _SORT_MAP 키

    Returns:
        QuerySet[User] — view에서 그대로 페이지네이터에 넘긴다.
    """
    qs = (
        User.objects.prefetch_related("dept_memberships__department")
        .select_related("position", "facility")
        .all()
    )

    name = (name or "").strip()
    if name:
        qs = qs.filter(name__icontains=name)

    if department_id:
        qs = qs.filter(
            dept_memberships__department_id=department_id,
            dept_memberships__is_primary=True,
        )

    if position_id:
        qs = qs.filter(position_id=position_id)

    if user_type:
        qs = qs.filter(user_type=user_type)

    # 계정 상태 — is_active와 account_locked_until 조합으로 판별.
    if account_status == "active":
        qs = qs.filter(is_active=True, account_locked_until=None)
    elif account_status == "locked":
        qs = qs.filter(is_active=True, account_locked_until__gt=timezone.now())
    elif account_status == "inactive":
        qs = qs.filter(is_active=False)

    return qs.order_by(_SORT_MAP.get(sort, _SORT_MAP[DEFAULT_SORT]))
