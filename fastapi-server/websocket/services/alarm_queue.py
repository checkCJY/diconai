# websocket/services/alarm_queue.py — Redis 기반 알람 큐
#
# Phase 1 C4 — 기존 메모리 list(`active_alarms`) + asyncio.Event(`alarm_signal`) 조합을
# 단일 Redis LIST + BRPOP으로 대체한다.
#
# 효과:
#   - FastAPI 재시작 시에도 큐가 휘발되지 않음
#   - LPUSH/BRPOP 자체가 원자 명령이라 신호 race(set/clear 손실) 해소
#   - 5개 슬라이스 cap 제거 — 큐 길이는 LTRIM으로만 제한
#
# 키 네임스페이스 `diconai:ws:alarms`는 Django RedisCache와 분리(`:1:` prefix 없음).
# IF §2 도입 시 `diconai:ws:alarms:recent:{event_id}`로 idempotency key 추가 예정.

import json
import logging

from core.redis_client import get_redis

ALARM_QUEUE_KEY = "diconai:ws:alarms"
MAX_QUEUE_LEN = 10_000  # 폭주 시 가장 오래된 알람부터 drop (LTRIM)

logger = logging.getLogger(__name__)


async def push_alarm(payload: dict) -> None:
    """알람 페이로드 1건을 큐 좌측에 push하고 길이를 cap한다.

    Celery → DRF /internal/alarms/push/ → 본 함수 경로로 들어오며,
    Redis 장애 시 예외는 호출자(HTTPException 503 등)에서 처리.
    """
    r = get_redis()
    await r.lpush(ALARM_QUEUE_KEY, json.dumps(payload, ensure_ascii=False))
    await r.ltrim(ALARM_QUEUE_KEY, 0, MAX_QUEUE_LEN - 1)


async def pop_alarm_blocking(timeout: int = 0) -> dict | None:
    """큐 우측에서 알람 1건을 blocking pop한다 (FIFO).

    timeout=0이면 무한 대기. ConnectionError 등 예외 시 None 반환해
    호출 루프가 다음 iteration에서 재시도하도록 한다 (slow-retry 패턴).
    """
    r = get_redis()
    try:
        result = await r.brpop(ALARM_QUEUE_KEY, timeout=timeout)
    except Exception as exc:
        logger.warning(f"[alarm_queue] action=brpop_error error={exc!r}")
        return None
    if result is None:
        return None
    _, raw = result
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(f"[alarm_queue] action=decode_error raw={raw!r} error={exc!r}")
        return None


async def queue_len() -> int:
    """관측·모니터링용 — 현재 큐에 적체된 알람 수. 메트릭에 사용."""
    r = get_redis()
    try:
        return int(await r.llen(ALARM_QUEUE_KEY))
    except Exception:
        return -1
