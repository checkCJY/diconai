"""
dashboard 메뉴 트리 조회 — Phase 4-a에서 DB 조회로 전환.

[변경 전 (3차)]
하드코딩 _MENU_WORKER + _MENU_ADMIN_EXTRA dict.

[변경 후 (Phase 4-a)]
Menu / RoleMenuVisibility / RoleProfile DB 조회 + Redis 캐시 (role별 5분 TTL).
운영자가 어드민에서 메뉴 추가/삭제하면 캐시 invalidate 후 즉시 반영.

[캐시 키]
"menu_tree:role:{role}"

[invalidate]
Menu / RoleMenuVisibility post_save / post_delete signal에서 모든 role 캐시 무효화.
"""

from django.core.cache import cache

from apps.core.metrics import CACHE_HIT_TOTAL, CACHE_MISS_TOTAL

_CACHE_PREFIX = "menu_tree"
_CACHE_TTL = 300  # 5분


def _cache_key(role: str) -> str:
    return f"{_CACHE_PREFIX}:role:{role}"


def get_menu_tree(role: str) -> list:
    """
    role(문자열, UserType.values 또는 RoleProfile.code)에 노출 가능한 SNB 메뉴 트리 반환.

    반환 형식 (3차와 동일하게 유지 — 프론트 영향 0):
        [
            {"id": "<menu.code>", "label": "<menu.name>", "icon": "...",
             "children": [
                 {"id": "...", "label": "...", "path": "..."},
                 ...
             ]},
            ...
        ]
    """
    cached = cache.get(_cache_key(role))
    if cached is not None:
        CACHE_HIT_TOTAL.labels(prefix="menu_tree").inc()
        return cached
    CACHE_MISS_TOTAL.labels(prefix="menu_tree").inc()
    tree = _build_menu_tree(role)
    cache.set(_cache_key(role), tree, _CACHE_TTL)
    return tree


def _build_menu_tree(role: str) -> list:
    """DB 조회 → role 기반 visibility 필터 → 트리 구성."""
    from apps.accounts.models import RoleProfile
    from apps.dashboard.models import Menu, RoleMenuVisibility

    # role 문자열을 RoleProfile.code로 매핑 (UserType과 동일 값)
    role_profile = RoleProfile.objects.filter(code=role, is_active=True).first()
    if role_profile is None:
        # RoleProfile 미존재 시 worker 기준 fallback
        role_profile = RoleProfile.objects.filter(code="worker", is_active=True).first()
    if role_profile is None:
        return []

    visible_menu_ids = set(
        RoleMenuVisibility.objects.filter(
            role_profile=role_profile, is_visible=True
        ).values_list("menu_id", flat=True)
    )
    if not visible_menu_ids:
        return []

    snb_menus = (
        Menu.objects.filter(
            id__in=visible_menu_ids, menu_type=Menu.MenuType.SNB, is_active=True
        )
        .select_related("parent")
        .order_by("sort_order", "code")
    )

    # 트리 구성: parent NULL이 최상위, 나머지는 children
    by_parent: dict[int | None, list] = {}
    for menu in snb_menus:
        by_parent.setdefault(menu.parent_id, []).append(menu)

    def to_node(menu):
        node: dict = {
            "id": menu.code,
            "label": menu.name,
        }
        if menu.icon:
            node["icon"] = menu.icon
        if menu.url_path:
            node["path"] = menu.url_path
        children = by_parent.get(menu.id)
        if children:
            node["children"] = [to_node(c) for c in children]
        return node

    return [to_node(m) for m in by_parent.get(None, [])]


def invalidate_menu_tree_cache() -> None:
    """Menu/RoleMenuVisibility 변경 시 모든 role 캐시 invalidate."""
    from apps.accounts.models import RoleProfile

    for code in RoleProfile.objects.values_list("code", flat=True):
        cache.delete(_cache_key(code))
