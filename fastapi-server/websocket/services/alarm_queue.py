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
#
# [Step 1 — fingerprint dedup]
# Celery `_push_to_ws` max_retries=3 retry 가 fastapi `/internal/alarms/push/` 로 같은
# payload 를 최대 3 번 보내 Redis 큐에 중복 적재되는 운영 버그를 choke point 에서 차단.
# 룰 알람은 event_id, AI 알람은 anomaly_meta(device/channel) 가 안정 idempotency key.

import json
import logging

from prometheus_client import Counter

from core.redis_client import get_redis

ALARM_QUEUE_KEY = "diconai:ws:alarms"
MAX_QUEUE_LEN = 10_000  # 폭주 시 가장 오래된 알람부터 drop (LTRIM)

# fingerprint 키 prefix — `redis-cli KEYS "alarm:push:dedup:*"` 로 모니터링 가능.
DEDUP_KEY_PREFIX = "alarm:push:dedup:"
# 기본 dedup TTL — Celery retry 간격 5s × max_retries 3 = 15s 보다 충분히 길고,
# RENOTIFY_COOLDOWN_MINUTES=1 (event_service) 보다 명확히 짧아야 1분 후 같은
# fingerprint 의 정상 재발화를 막지 않는다.
#
# [hard requirement 아님, 가독성·예측가능성 마진]
# race 발생해도 결과는 "한 cycle 누락" 이지 "잘못된 알림 발사" 아님 — 최대 1분
# 지연 수준. 그러나 cooldown(60s) 과 동일 TTL 두면 만료 타이밍 race 가독성 저하
# 라 30s 로 마진. 운영 데이터 후 재평가.
PUSH_DEDUP_TTL_SEC = 30

logger = logging.getLogger(__name__)

# Prometheus — fingerprint dedup 으로 차단된 중복 push 횟수.
# 운영 중 retry 폭주 / 인프라 장애 추세 추적용. label 없음 (단일 게이트).
push_alarm_dedup_hits = Counter(
    "alarm_push_dedup_hits_total",
    "Celery retry 등으로 인한 중복 push 가 fingerprint dedup 으로 차단된 횟수",
)


def _payload_fingerprint(payload: dict) -> str | None:
    """push payload 의 dedup fingerprint 를 계산한다.

    룰 알람은 `event_id` 가 안정 idempotency key (Celery retry 는 같은 task →
    같은 event_id, 같은 risk_level). AI 알람은 forward 시점에 event_id 가 없으므로
    `anomaly_meta` 의 device/channel + risk_level 조합으로 대체.

    fingerprint 형식을 판단할 수 없는 payload (clear notification, geofence 등)
    는 None 반환 → dedup 자체 skip (백워드 호환).

    Returns:
        Redis 키 suffix 로 쓰일 fingerprint. None 이면 dedup 미적용.
    """
    risk_level = payload.get("risk_level", "unknown")

    event_id = payload.get("event_id")
    if event_id is not None:
        return f"event:{event_id}:{risk_level}"

    alarm_type = payload.get("alarm_type", "")
    if alarm_type == "power_anomaly_ai":
        meta = payload.get("anomaly_meta") or {}
        device_id = meta.get("device_id")
        channel = meta.get("channel")
        if device_id is None or channel is None:
            return None
        return f"ai:{alarm_type}:{device_id}:{channel}:{risk_level}"

    return None


async def push_alarm(payload: dict, *, dedup_ttl: int = PUSH_DEDUP_TTL_SEC) -> None:
    """알람 페이로드 1건을 큐 좌측에 push — fingerprint dedup 으로 중복 차단.

    Celery → DRF `/internal/alarms/push/` → 본 함수 경로로 들어온다. Celery
    `_push_to_ws` 의 retry 가 같은 payload 를 여러 번 보내는 운영 버그를 본 함수에서
    SET NX EX idempotency 키로 막아, 첫 도착자만 LPUSH 하고 후속 retry 는 silently
    drop 한다. Redis 장애 시 예외는 호출자 (HTTPException 503 등) 에서 처리.

    [SET NX EX 가 LPUSH 보다 먼저 실행되는 이유]
    첫 set 성공 → LPUSH 성공이 일반 경로. LPUSH 만 부분 실패 (Redis 일시 hang) 시
    set 잔류로 retry 가 dedup 되어 알람 누락될 수 있으나, 같은 Redis 인스턴스의 두
    명령이 부분 실패하는 케이스는 매우 드물고 인프라 알람으로 잡혀야 한다. retry
    중복 (자주 발생) 차단 효과가 누락 위험 (희소) 보다 명백히 크다.

    Args:
        payload: 알람 dict. event_id 있으면 룰, anomaly_meta 있으면 AI 로 분기.
        dedup_ttl: fingerprint 키 TTL (기본 60s). 테스트에서 0.1s 등 짧게 인자화 가능.
    """
    r = get_redis()
    fp = _payload_fingerprint(payload)
    if fp is not None:
        dedup_key = DEDUP_KEY_PREFIX + fp
        # 첫 도착자만 True. retry/중복은 False → silently drop + counter inc.
        if not await r.set(dedup_key, "1", nx=True, ex=dedup_ttl):
            push_alarm_dedup_hits.inc()
            logger.info("[push_alarm] dedup hit fp=%s", fp)
            return
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
