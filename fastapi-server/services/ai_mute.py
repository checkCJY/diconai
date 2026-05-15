"""AI 발화 시 룰 알람 mute 마킹 헬퍼 — fastapi → Redis 직접.

[목적]
AI 추론 알람이 발화 (push) 하는 순간, 같은 (device, channel) 의 룰 알람 (DRF 측
`apps.monitoring.services.power_alarm.trigger_power_alarms`) 을 60s 동안 suppress
하도록 Redis 에 마킹. DRF 측 `apps.alerts.services.alarm_dedupe.is_ai_mute_active`
가 본 모듈이 set 한 키를 raw redis EXISTS 로 read.

[양쪽 호환 보장]
fastapi 와 DRF 양쪽이 raw redis 클라이언트로 같은 키를 직접 set/exists. Django
RedisCache 의 pickle 직렬화·KEY_PREFIX 영향 없음 (try_transition 패턴과 동일).
키 형식은 DRF `alarm_dedupe._AI_FIRED_KEY_TEMPLATE` 와 정확히 일치해야 한다.

[격상 bypass]
mark_ai_recent 는 발화 level '이하' 키만 set (warning 발화 → normal/warning 만,
danger 키 부재). DRF 측 가드는 룰이 발화하려는 level 키만 보므로 격상 케이스
(AI=warning, 룰=danger) 는 자연 통과.
"""

import logging

from core.redis_client import get_redis

logger = logging.getLogger(__name__)

# AI 발화 mute TTL — DRF AI_MUTE_TTL_SEC / power_service.RATE_LIMIT_SEC 와 일치.
AI_MUTE_TTL_SEC = 60

# 룰 위험도 순서 — 격상 bypass 키 설계용 (DRF _LEVELS_AT_OR_BELOW 와 동일).
_LEVELS_AT_OR_BELOW: dict[str, list[str]] = {
    "normal": ["normal"],
    "warning": ["normal", "warning"],
    "danger": ["normal", "warning", "danger"],
}


async def mark_ai_recent(
    device_id: str | int | None,
    channel: int | None,
    rule_level: str,
    ttl_sec: int = AI_MUTE_TTL_SEC,
) -> None:
    """AI 발화를 Redis 에 마킹 — DRF 룰 가드가 같은 키 read.

    silent fail — Redis 장애가 알람 push 흐름을 막지 않도록 예외는 logger.warning
    으로만 swallow. 마킹 실패 시 룰 가드가 작동 안 해 중복 알람 1회 노출되는 정도
    (수용 가능 degradation, [[runtime_docker_environment]]).

    Args:
        device_id: PowerDevice 식별자 (DRF PowerDevice.id 와 일치). None 이면 skip.
        channel: PowerData.channel (1~16). None 이면 skip.
        rule_level: AI_TO_RULE_LEVEL 로 환산된 룰 위험도. 'warning'|'danger' 만 의미
            있음 ('normal' 은 어차피 룰도 fire 안 함).
        ttl_sec: mute 유지 시간 (기본 60s, 테스트에서 짧게 인자화 가능).
    """
    if device_id is None or channel is None:
        return
    if rule_level not in _LEVELS_AT_OR_BELOW:
        logger.warning("[ai_mute] unknown rule_level=%s — skip mark", rule_level)
        return

    try:
        r = get_redis()
        for lv in _LEVELS_AT_OR_BELOW[rule_level]:
            key = f"ai_fired:{device_id}:{channel}:{lv}"
            await r.set(key, "1", ex=ttl_sec)
    except Exception:
        logger.warning(
            "[ai_mute] mark failed device=%s ch=%s lv=%s — silent fail",
            device_id,
            channel,
            rule_level,
        )
