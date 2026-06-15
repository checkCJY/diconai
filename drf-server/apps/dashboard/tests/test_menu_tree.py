"""
메뉴 트리 회귀 테스트 (Phase 1~4 회귀 점검 Step 3) — 단위 테스트.

[회귀 커버 대상]
- Phase 4-a dashboard/menu.py DB 조회 전환:
  - get_menu_tree(role)이 RoleProfile + RoleMenuVisibility + Menu DB 조회
  - 반환 형식 (3차와 동일): [{id, label, icon?, path?, children?}]
- worker는 admin_only/admin_history 제외 (Phase 4 PR1 시드)
- super_admin은 모든 메뉴 포함
- 미존재 role은 worker fallback (graceful)
- Redis 캐시 (5분 TTL) 동작 + signal invalidate
- snake_case 코드 (이전 SNB-XX 형식 폐기)

[설계 결정]
plan §9-4 권장: 메뉴 트리는 단위 권장. 함수 입출력 단순.
"""

import pytest
from django.core.cache import cache

from apps.dashboard.menu import (
    _cache_key,
    get_menu_tree,
    invalidate_menu_tree_cache,
)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_worker_menu_tree_excludes_admin_only(db):
    """worker는 admin_only / admin_history 메뉴 제외."""
    tree = get_menu_tree("worker")
    top_codes = {node["id"] for node in tree}
    assert "safety" in top_codes
    assert "monitoring" in top_codes
    assert "admin_only" not in top_codes


@pytest.mark.django_db
def test_super_admin_menu_tree_includes_admin_only(db):
    """super_admin은 admin_only 메뉴까지 모두 포함."""
    tree = get_menu_tree("super_admin")
    top_codes = {node["id"] for node in tree}
    assert "admin_only" in top_codes


@pytest.mark.django_db
def test_menu_codes_are_snake_case(db):
    """모든 메뉴 코드가 snake_case (이전 'SNB-01' 형식 폐기)."""

    def collect_codes(nodes):
        for n in nodes:
            yield n["id"]
            for child in n.get("children", []):
                yield from collect_codes([child])

    tree = get_menu_tree("super_admin")
    codes = list(collect_codes(tree))
    assert codes
    for code in codes:
        assert "-" not in code, f"하이픈 형식 코드 잔존: {code}"
        assert code == code.lower()


@pytest.mark.django_db
def test_menu_tree_response_shape(db):
    """반환 형식 구조: id/label/children 키."""
    tree = get_menu_tree("worker")
    assert tree
    for node in tree:
        assert "id" in node
        assert "label" in node
        # children이 있는 경우만 자식 검증
        for child in node.get("children", []):
            assert "id" in child
            assert "label" in child
            # 잎 노드는 path 보유
            if "children" not in child:
                assert "path" in child


@pytest.mark.django_db
def test_menu_tree_uses_cache_on_second_call(db):
    """두 번째 호출은 캐시 hit (DB 안 침)."""
    tree1 = get_menu_tree("worker")
    cached = cache.get(_cache_key("worker"))
    assert cached is not None
    assert cached == tree1

    tree2 = get_menu_tree("worker")
    assert tree2 == tree1


@pytest.mark.django_db
def test_invalidate_menu_tree_cache_clears_all_roles(db):
    """invalidate_menu_tree_cache()로 모든 role 캐시 무효화."""
    get_menu_tree("worker")
    get_menu_tree("super_admin")
    assert cache.get(_cache_key("worker")) is not None
    assert cache.get(_cache_key("super_admin")) is not None

    invalidate_menu_tree_cache()
    assert cache.get(_cache_key("worker")) is None
    assert cache.get(_cache_key("super_admin")) is None


@pytest.mark.django_db
def test_unknown_role_falls_back_to_worker(db):
    """미존재 role은 worker로 fallback (graceful)."""
    tree = get_menu_tree("nonexistent_role")
    worker_tree = get_menu_tree("worker")
    assert tree == worker_tree
