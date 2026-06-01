# apps/alerts/services/alarm_dedupe.py — 알람 상태 천이 원자화 + AI 우선순위 mute
#
# Redis Lua로 GET→CMP→SET을 단일 명령으로 실행해 gas_alarm/power_alarm의
# cache.get → fire_task.delay → cache.set 비원자 패턴을 원자화한다. 동시 다중
# 수신 시 중복 fire를 방지.
#
# Django RedisCache와 같은 키 공간/직렬화(피클)를 사용해 try_transition이
# SET한 값을 cache.get/cache.add 등 기존 코드 경로에서도 그대로 읽을 수
# 있도록 보장한다.
#
# AI 우선순위 mute: AI 추론 알람이 발화하면 같은 (device, channel) 의 룰 알람을
# 60s 동안 mute 한다. AI 가 fastapi 측에서 Redis 에 직접 마킹한 키를 본 모듈의
# 헬퍼가 읽어 가드. 격상 (warning AI → danger 룰) 케이스는 mute 키가 level 별로
# 분리돼 있어 자연 bypass — 별도 분기 로직 불요.

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


# AI 발화 시 룰 mute 가드

# 룰 위험도의 순서 — 격상 bypass 키 설계용.
# AI 가 warning 발화 시 normal·warning 키만 set → 룰 danger 들어오면 danger 키 부재
# → mute 해제 → fire. 격상은 "더 높은 level 키가 없으면 통과" 로 자연 표현된다.
_LEVELS_AT_OR_BELOW: dict[str, list[str]] = {
    "normal": ["normal"],
    "warning": ["normal", "warning"],
    "danger": ["normal", "warning", "danger"],
}

# Redis 키 prefix — fastapi `services/ai_mute.py` 와 동일 포맷. 양쪽이 raw redis
# 클라이언트 (`_redis()`) 로 키를 set/exists 하므로 Django RedisCache 의 pickle
# 직렬화·prefix 영향을 받지 않고 동일 raw 키 공간을 공유한다. 키 형식 변경 시
# 양쪽 동시 갱신 필수.
_AI_FIRED_KEY_TEMPLATE = "ai_fired:{device_id}:{channel}:{rule_level}"

# 기본 mute TTL — power_service.RATE_LIMIT_SEC 와 일치. AI 가 같은 채널을 60s 에
# 최대 1번 발화하므로 mute 도 그 주기에 맞춰 회수된다.
AI_MUTE_TTL_SEC = 60


def mark_ai_recent(
    device_id: int | str,
    channel: int,
    rule_level: str,
    ttl_sec: int = AI_MUTE_TTL_SEC,
) -> None:
    """AI 발화를 Redis 에 마킹 — 같은 채널의 룰 알람을 ttl_sec 동안 mute 한다.

    발화 level '이하' 키를 모두 set 함으로써 격상 bypass 를 보장한다 (예: warning
    발화면 normal/warning 키만 set, danger 키 부재 → 룰 danger 자유 통과). DRF
    측 호출은 통합 테스트·가스 AI 후속 sprint 의 가스 룰 가드용. 운영에선 fastapi
    `services.ai_mute.mark_ai_recent` 가 같은 키 공간에 마킹한다.

    raw redis 사용 — try_transition 패턴과 일치. cache.set 의 pickle 직렬화 회피.

    Args:
        device_id: 식별자. **fastapi 가 set 하는 것과 일치해야 한다** — 운영에선 IoT
            raw id (PowerDevice.device_id, 예: mac 주소) 를 쓴다. PK (PowerDevice.id)
            로 마킹/조회 시 fastapi 키와 mismatch → 가드 부재. 가스 도메인 확장 시
            sensor 의 raw device_id 도 동일 원칙.
        channel: PowerData.channel (1~16) 또는 가스 0 등.
        rule_level: AI 발화 레벨을 AI_TO_RULE_LEVEL 로 환산한 결과 ('warning'|'danger').
            'normal' 도 가능하나 그 경우 어차피 룰도 fire 안 함이라 의미 없음.
        ttl_sec: mute 유지 시간. 테스트에서 짧게 인자화 가능 (0.1s 등).
    """
    redis = _redis()
    for lv in _LEVELS_AT_OR_BELOW.get(rule_level, [rule_level]):
        key = _AI_FIRED_KEY_TEMPLATE.format(
            device_id=device_id, channel=channel, rule_level=lv
        )
        redis.set(key, "1", ex=ttl_sec)


def is_ai_mute_active(device_id: int | str, channel: int, rule_level: str) -> bool:
    """룰이 rule_level 로 발화하려 할 때 mute 상태인지 확인.

    raw redis EXISTS — rule_level 키만 본다. 격상 케이스 (룰 danger, AI 가 warning
    만 set) 는 danger 키 부재 → False → mute 해제 → 룰 fire 진행. 같거나 낮은
    level 의 룰 발화만 suppress 된다 (운영 의도와 일치).

    Redis 장애 시 False 반환 (fail-open) — mute 가드 실패가 알람 발화 흐름을
    막으면 안 됨. 인프라 장애는 별도 모니터링.
    """
    key = _AI_FIRED_KEY_TEMPLATE.format(
        device_id=device_id, channel=channel, rule_level=rule_level
    )
    try:
        return bool(_redis().exists(key))
    except Exception:
        return False


# 가스 도메인 — fastapi services/ai_mute.py 의 mark_gas_ai_recent 와 동일 키 형식.
# prefix `ai_fired_gas:*` 로 power 와 분리. 추론 가스 3종 (co/h2s/co2) 만 적용.
_GAS_AI_FIRED_KEY_TEMPLATE = "ai_fired_gas:{sensor_id}:{gas_type}:{rule_level}"


def is_gas_ai_mute_active(sensor_id: int, gas_type: str, rule_level: str) -> bool:
    """가스 룰 발화 직전 mute 가드 — AI 가 추론 가스에 발화 시 60s 정적 룰 억제.

    호출자(gas_alarm.trigger_gas_alarms) 가 gas in ('co','h2s','co2') 필터링 후
    호출하므로 본 함수는 가스 종류 제한 안 함.
    """
    key = _GAS_AI_FIRED_KEY_TEMPLATE.format(
        sensor_id=sensor_id, gas_type=gas_type, rule_level=rule_level
    )
    try:
        return bool(_redis().exists(key))
    except Exception:
        return False
