"""
pytest 공통 fixture (Phase 1~4 회귀 테스트용).
"""

import pytest


# 이성현 수정 — DummyCache → LocMemCache로 교체
# DummyCache는 완전한 가짜라 _cache 속성이 없어 test_ai_mute_guard.py 에서 오류 발생.
# LocMemCache는 메모리 기반 실제 캐시 — Redis 없이도 get/set/delete 전부 동작.
@pytest.fixture(autouse=True)
def use_dummy_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }


# 이성현 수정 — sqlsequencereset 커맨드 → conn.ops.sequence_reset_sql() 직접 호출로 교체
# sqlsequencereset 커맨드는 output_transaction=True 설정으로 BEGIN;/COMMIT; 을 출력에 포함시킴.
# split(";\n")으로 나눠서 실행하면 COMMIT 이 테스트 프레임워크의 트랜잭션을 깨뜨려
# 전체 세션 오류로 이어짐. ops.sequence_reset_sql()은 SELECT setval(...)만 반환 — 안전함.
@pytest.fixture(scope="session", autouse=True)
def reset_sequences(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        from django.apps import apps as django_apps
        from django.core.management.color import no_style
        from django.db import connections

        conn = connections["default"]
        stmts = []
        for app_config in django_apps.get_app_configs():
            stmts.extend(
                conn.ops.sequence_reset_sql(no_style(), list(app_config.get_models()))
            )

        if stmts:
            with conn.cursor() as cursor:
                for stmt in stmts:
                    try:
                        cursor.execute(stmt)
                    except Exception:
                        pass


@pytest.fixture
def facility(db):
    from apps.facilities.models import Facility

    return Facility.objects.create(
        name="회귀 점검 공장",
        address="테스트시 회귀구 1-2",
    )


@pytest.fixture
def gas_sensor(db, facility):
    from apps.facilities.models import GasSensor

    return GasSensor.objects.create(
        facility=facility,
        device_id="GAS-REGRESS-01",
        device_name="회귀 점검 가스 센서",
        x=10.0,
        y=20.0,
    )


@pytest.fixture
def power_device(db, facility):
    from apps.facilities.models import PowerDevice

    return PowerDevice.objects.create(
        facility=facility,
        device_id="POW-REGRESS-01",
        device_name="회귀 점검 전력 장비",
        x=30.0,
        y=40.0,
    )


@pytest.fixture
def position_node(db, facility):
    from apps.facilities.models import PositionNode

    return PositionNode.objects.create(
        facility=facility,
        device_id="NODE-REGRESS-01",
        device_name="회귀 점검 위치 노드",
        x=50.0,
        y=60.0,
    )


@pytest.fixture
def worker_user(db):
    from apps.accounts.models import CustomUser

    return CustomUser.objects.create_user(
        username="regress_worker",
        password="regress-pass-1!",
        user_type="worker",
        name="회귀 작업자",
    )
