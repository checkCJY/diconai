"""
pytest 공통 fixture (Phase 1~4 회귀 테스트용).
"""

import pytest


# 테스트 캐시 = production 과 동일한 RedisCache (단, DB 15 격리).
#
# 배경: 알람 dedup(`alarm_dedupe.try_transition`/`mark_ai_recent`)은 raw redis-py
# 클라이언트의 Lua eval(`cache._cache.get_client()`)을 직접 호출한다. LocMemCache·
# DummyCache 는 `get_client()`가 없어 AttributeError 로 깨진다(채널-aware clear /
# AI mute / 2틱 confirm 테스트 13종). 따라서 이 경로를 검증하려면 실제 Redis 가 필요.
#
# DB 15 = 운영/celery(DB 0)와 분리된 테스트 전용 공간. 매 테스트 전후 flush 로 키 격리.
@pytest.fixture(autouse=True)
def use_redis_cache(settings):
    from django.conf import settings as dj_settings

    base_url = getattr(dj_settings, "REDIS_URL", "redis://localhost:6379/0")
    # …/0 → …/15 로 DB 번호만 교체 (스킴/호스트/포트 보존)
    test_url = base_url.rsplit("/", 1)[0] + "/15"
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": test_url,
        }
    }

    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


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
