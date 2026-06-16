"""
alarm_dedupe 의 원자성·fail-safe 회귀 가드 (P0 신규).

- try_transition: race-safe 천이 — 동시 N 호출 중 정확히 1개만 True (Lua eval 원자성).
  cache.get→fire→cache.set 비원자 패턴이면 중복 발화가 생기던 자리.
- is_ai_mute_active / is_gas_ai_mute_active: Redis 장애 시 fail-open (False 반환,
  예외 미전파) — 캐시가 죽어도 알람이 suppress 되지 않고 정상 발화하도록 하는 의도된
  silent-except 임을 명문화. (alarm_dedupe.py 의 `except Exception: return False`)
"""

import threading
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.alerts.services.alarm_dedupe import (
    is_ai_mute_active,
    is_gas_ai_mute_active,
    try_transition,
)
from apps.core.constants import RiskLevel


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_try_transition_first_call_wins_same_state():
    """같은 new_state 연속 호출 — 첫 호출만 True, 이후 False (중복 fire 차단)."""
    key = "power_state:1:1"
    assert try_transition(key, RiskLevel.DANGER) is True  # normal → danger 천이
    assert try_transition(key, RiskLevel.DANGER) is False  # 이미 danger — skip
    assert try_transition(key, RiskLevel.NORMAL) is True  # danger → normal 천이
    assert try_transition(key, RiskLevel.NORMAL) is False  # 이미 normal — skip


def test_try_transition_concurrent_exactly_one_winner():
    """동시 N 스레드가 같은 천이를 시도 → 정확히 1개만 True (Lua 원자성 race-safe).

    barrier 로 N 스레드를 동시 출발시켜 race 압박을 극대화한다. redis Lua eval 은
    단일 스레드에서 직렬 실행되어 정확히 1개만 GET nil → SET 에 성공한다.
    """
    key = "power_state:99:1"
    n = 20
    results: list[bool] = []
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()  # 동시 출발 정렬
        results.append(try_transition(key, RiskLevel.DANGER))

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == n
    assert sum(1 for r in results if r) == 1  # 단 1개만 fire 권한 획득


def test_is_ai_mute_active_failopen_on_redis_error():
    """Redis 장애 시 mute 체크는 False(fail-open) — 알람이 suppress 되지 않게.

    is_ai_mute_active 의 silent except 는 버그를 삼키는 게 아니라 의도된 fail-open:
    캐시가 죽어 mute 판정이 불가하면 '발화 허용' 쪽으로 안전하게 떨어진다. 예외가
    호출자(power_alarm.trigger_power_alarms)로 전파되면 알람 파이프라인 전체가 깨진다.
    """
    with patch(
        "apps.alerts.services.alarm_dedupe._redis",
        side_effect=ConnectionError("redis down"),
    ):
        assert is_ai_mute_active("dev-1", 1, RiskLevel.DANGER) is False
        assert is_gas_ai_mute_active(1, "co", RiskLevel.DANGER) is False
