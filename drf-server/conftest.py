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


# 이성현 수정 — django_db_setup 오버라이드 → 별도 autouse 세션 픽스처로 교체
# 기존 django_db_setup 오버라이드는 TestCase 기반 테스트와 실행 순서가 충돌하여
# PG 시퀀스 리셋이 적용되지 않는 경우가 발생함.
# sqlsequencereset(Django 내장 커맨드)를 통해 각 앱 모델의 시퀀스를 정확히 리셋.
# autouse + scope="session" → 모든 테스트(pytest/TestCase 무관) 시작 전 1회 실행 보장.
@pytest.fixture(scope="session", autouse=True)
def reset_sequences(django_db_setup, django_db_blocker):
    import io

    from django.apps import apps as django_apps
    from django.core.management import call_command
    from django.db import connection

    with django_db_blocker.unblock():
        buf = io.StringIO()
        call_command(
            "sqlsequencereset",
            *[a.label for a in django_apps.get_app_configs()],
            stdout=buf,
            no_color=True,
        )
        with connection.cursor() as cursor:
            for stmt in (s.strip() for s in buf.getvalue().split(";\n") if s.strip()):
                cursor.execute(stmt)


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
