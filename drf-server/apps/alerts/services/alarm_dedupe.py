# apps/alerts/services/alarm_dedupe.py — 알람 상태 천이 원자화
#
# Phase 1 C2 — Redis Lua로 GET→CMP→SET을 단일 명령으로 실행해
# gas_alarm/power_alarm의 cache.get → fire_task.delay → cache.set 비원자
# 패턴을 원자화한다. 동시 다중 수신 시 중복 fire를 방지.
#
# Django RedisCache와 같은 키 공간/직렬화(피클)를 사용해 try_transition이
# SET한 값을 cache.get/cache.add 등 기존 코드 경로에서도 그대로 읽을 수
# 있도록 보장한다.
#
# 향후 IF §2-3-a에서 state_key에 `:threshold`/`:anomaly` 접미사를 도입할 때도
# 본 모듈의 시그니처는 변경 없이 그대로 재사용된다.

import pickle

from django.core.cache import cache

# KEYS[1] = cache.make_key(state_key)로 prefix 적용된 raw redis 키
# ARGV[1] = pickle 직렬화된 new_state 값
# ARGV[2] = TTL seconds
# return 1 = 천이 성공(이전 상태와 다름, fire 필요), 0 = 동일 상태(skip)
_TRANSITION_LUA = """
local cur = redis.call('GET', KEYS[1])
if cur == ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return 1
"""


def _redis():
    """Django built-in RedisCache의 raw redis-py 클라이언트를 반환한다."""
    return cache._cache.get_client()


def try_transition(state_key: str, new_state: str, ttl: int = 3600) -> bool:
    """현재 상태가 new_state와 다를 때만 원자적으로 SET. 천이 성공 시 True.

    동시 다중 호출 중 정확히 1개만 True를 받고 나머지는 False — 호출자가
    이 반환값으로 fire_*_task.delay() 호출 여부를 결정하면 race가 차단된다.
    """
    full_key = cache.make_key(state_key)
    pickled = pickle.dumps(new_state)
    return bool(_redis().eval(_TRANSITION_LUA, 1, full_key, pickled, ttl))


def get_state(state_key: str, default: str = "normal") -> str:
    """현재 알람 상태를 반환. 키 없음/만료는 default."""
    val = cache.get(state_key)
    return val if val is not None else default


def clear_state(state_key: str) -> None:
    """알람 상태 키를 삭제(정상 복귀). 다음 try_transition에서 어떤 상태든 천이 가능."""
    cache.delete(state_key)
