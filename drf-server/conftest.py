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


# 이성현 추가 — PG 시퀀스 리셋 (마이그레이션 시드 후 중복 키 충돌 방지)
# 마이그레이션이 id=1로 데이터를 심으면 PG 시퀀스가 갱신되지 않아
# 첫 테스트에서 id=1을 또 만들려다 충돌남. 시퀀스를 max(id)로 맞춰줌.
@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        from django.core.management import call_command

        call_command("reset_pg_sequences")


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


# 이성현 추가 — 테스트 중 Redis 의존 제거
# CI 환경에서 Redis 없이도 테스트가 실행되도록 더미 캐시로 교체.
# cache.clear() / cache.get() / cache.set() 호출은 모두 아무것도 안 하는 상태로 동작.
@pytest.fixture(autouse=True)
def use_dummy_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        }
    }
