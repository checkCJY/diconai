# websocket/services/alarm_queue.py — Redis 기반 알람 큐
#
# Phase 1 C4 — 기존 메모리 list(`active_alarms`) + asyncio.Event(`alarm_signal`) 조합을
# Redis 큐로 대체했다. 이후 fan-out 멀티레플리카 대비로 LIST+BRPOP → Stream+XREAD 전환.
#
# 현 구조: XADD(MAXLEN ~) 로 적재하고, replica 별 독립 XREAD 가 자기 커서(last_id)로
# 스트림 전체를 읽는다. BRPOP(경쟁 소비 — 한 알람을 한 소비자만 pop)과 달리 모든 replica
# 가 모든 알람을 받는 fan-out. Consumer Group 미사용 (그룹은 경쟁 분배라 fan-out 불가).
#
# 효과:
#   - FastAPI 재시작 시에도 큐가 휘발되지 않음
#   - XADD 자체가 원자 명령이라 신호 race(set/clear 손실) 해소
#   - 큐 길이 cap 은 XADD 의 MAXLEN ~ 로 제한 (별도 트리밍 명령 불필요)
#
# 키 네임스페이스 `diconai:ws:alarms`는 Django RedisCache와 분리(`:1:` prefix 없음).
#
# [Step 1 — fingerprint dedup]
# Celery `_push_to_ws` max_retries=3 retry 가 fastapi `/internal/alarms/push/` 로 같은
# payload 를 최대 3 번 보내 Redis 큐에 중복 적재되는 운영 버그를 choke point 에서 차단.
# 룰 알람은 event_id, AI 알람은 anomaly_meta(device/channel) 가 안정 idempotency key.

import json
import logging
import time

from prometheus_client import Counter

from core.metrics import ALARM_QUEUE_LENGTH, REDIS_COMMAND_DURATION
from core.redis_client import get_redis

ALARM_QUEUE_KEY = "diconai:ws:alarms"
MAX_QUEUE_LEN = 10_000  # 폭주 시 가장 오래된 알람부터 drop (XADD MAXLEN ~)

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
        # 2026-05-15 알람 재설계: RESOLVED 신호는 원래 알람과 같은 (event_id, risk_level)
        # 조합이라 기본 fingerprint 로는 dedup 차단됨 (운영 버그). 별도 suffix 로 분리해
        # RESOLVED 신호 자체의 retry 중복은 막되 원래 알람과는 독립 trackin.
        if payload.get("event_resolved_at"):
            return f"event:{event_id}:resolved"
        return f"event:{event_id}:{risk_level}"

    alarm_type = payload.get("alarm_type", "")
    if alarm_type == "power_anomaly_ai":
        meta = payload.get("anomaly_meta") or {}
        device_id = meta.get("device_id")
        channel = meta.get("channel")
        if device_id is None or channel is None:
            return None
        return f"ai:{alarm_type}:{device_id}:{channel}:{risk_level}"

    # 정상화 알람 — gas 센서는 9 종 (co/h2s/co2/o2/no2/so2/o3/nh3/voc) 각각이
    # 별도 fire_clear_notification_task 를 발화 → 같은 source_label 9 push 가
    # 30s 안에 동시 도착. source_label 단위로 dedup 해서 패널 1줄만 노출.
    # source_label 누락 시 (이론상 없음) None 반환 → 백워드 호환.
    if alarm_type in ("gas_clear", "power_clear"):
        source_label = payload.get("source_label", "")
        if not source_label:
            return None
        return f"clear:{alarm_type}:{source_label}"

    # T4 D2 patch — power_overload + T4 source 분기 (static_cover_* / static_no_ai_available).
    # process_anomaly_inference 가 모든 채널 매 sample 평가 → 같은 (source, channel)
    # 조합이 매초 push 됐던 폭주 차단. event_id 분기보다 후행이라 룰 알람 (event_id
    # 있음) 영향 없음. fingerprint key 에 source_label 포함 — 같은 채널 의 같은 risk
    # 가 30s 안 1회만 통과. AI source (decision.source=='ai') 는 위 anomaly_meta
    # 분기 (ai:*) 우선이라 본 분기 미진입.
    if alarm_type == "power_overload":
        source = payload.get("source")
        source_label = payload.get("source_label", "")
        if not source or not source_label:
            return None  # 옛 발신자 / 정보 부족 — dedup 미적용 (백워드 호환)
        return f"cover:{source}:{source_label}:{risk_level}"

    return None


async def push_alarm(payload: dict, *, dedup_ttl: int = PUSH_DEDUP_TTL_SEC) -> None:
    """알람 페이로드 1건을 스트림에 XADD — fingerprint dedup 으로 중복 차단.

    Celery → DRF `/internal/alarms/push/` → 본 함수 경로로 들어온다. Celery
    `_push_to_ws` 의 retry 가 같은 payload 를 여러 번 보내는 운영 버그를 본 함수에서
    SET NX EX idempotency 키로 막아, 첫 도착자만 XADD 하고 후속 retry 는 silently
    drop 한다. Redis 장애 시 예외는 호출자 (HTTPException 503 등) 에서 처리.

    [SET NX EX 가 XADD 보다 먼저 실행되는 이유]
    첫 set 성공 → XADD 성공이 일반 경로. XADD 만 부분 실패 (Redis 일시 hang) 시
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
    # P1 — XADD 실행시간 측정. E2E latency 급등 시 Redis 병목 여부 판단 근거.
    # MAXLEN ~ 10000 으로 트리밍을 XADD 에 포함 (approximate=True → 별도 LTRIM 불필요).
    # payload 는 단일 필드 "data" 에 JSON 직렬화해 저장 (read 시 json.loads 복원).
    _t = time.perf_counter()
    await r.xadd(
        ALARM_QUEUE_KEY,
        {"data": json.dumps(payload, ensure_ascii=False)},
        maxlen=MAX_QUEUE_LEN,
        approximate=True,
    )
    REDIS_COMMAND_DURATION.labels("xadd").observe(time.perf_counter() - _t)
    ALARM_QUEUE_LENGTH.set(await queue_len())


async def read_alarms_blocking(
    last_id: str, timeout: int = 0
) -> tuple[str, list[dict]]:
    """커서(last_id) 이후 쌓인 알람을 XREAD BLOCK 으로 한 번에 읽는다 (FIFO).

    BRPOP(경쟁 소비, 1건씩)과 달리 XREAD 는 커서 이후 누적된 N 건을 배치로 준다.
    커서는 호출자가 보유한다 — 각 replica 가 자기 last_id 로 스트림 전체를 읽는
    fan-out 구조의 핵심. timeout=0 이면 무한 대기.

    Args:
        last_id: 직전까지 읽은 마지막 entry ID. 부팅 직후 신규만 받으려면 "$".
        timeout: XREAD BLOCK 초. 0 이면 무한 대기 (BRPOP timeout=0 과 동일 시맨틱).

    Returns:
        (new_last_id, payloads) 튜플.
        - new_last_id: 배치 마지막 entry ID. 빈 결과/예외면 입력 last_id 그대로
          (커서 전진 금지 — 다음 iteration 이 같은 지점부터 재시도).
        - payloads: 배치에 담긴 알람 dict 리스트 (순서 보존). 빈 결과면 [].

    예외(ConnectionError 등) 시 (last_id, []) 반환해 호출 루프가 다음 iteration
    에서 재시도하도록 한다 (slow-retry 패턴).
    """
    r = get_redis()
    try:
        # BLOCK 은 ms 단위. timeout=0 → BLOCK 0 → 무한 대기 (BRPOP 과 동일).
        # XREAD 대기시간은 측정하지 않는다 — BLOCK 대기가 섞여 무의미 (BRPOP 과
        # 동일 이유, REDIS_COMMAND_DURATION 은 XADD 만 측정).
        result = await r.xread({ALARM_QUEUE_KEY: last_id}, block=timeout * 1000)
    except Exception as exc:
        logger.warning(f"[alarm_queue] action=xread_error error={exc!r}")
        return last_id, []
    if not result:
        # BLOCK timeout (신규 entry 없음) — 커서 유지, 다음 iteration 계속.
        return last_id, []
    # result: [(stream_key, [(entry_id, {"data": <json>}), ...])]. 키 1개라 [0].
    _, entries = result[0]
    new_last_id = last_id
    payloads: list[dict] = []
    for entry_id, fields in entries:
        new_last_id = entry_id  # 배치 마지막 entry ID 로 커서 전진
        raw = fields.get("data")
        try:
            payloads.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                f"[alarm_queue] action=decode_error id={entry_id} "
                f"raw={raw!r} error={exc!r}"
            )
    ALARM_QUEUE_LENGTH.set(await queue_len())
    return new_last_id, payloads


async def queue_len() -> int:
    """관측·모니터링용 — 현재 스트림에 적체된 알람 수 (XLEN). 메트릭에 사용."""
    r = get_redis()
    try:
        return int(await r.xlen(ALARM_QUEUE_KEY))
    except Exception:
        return -1


async def reset_stream_if_wrongtype() -> None:
    """잔존 LIST 키만 1회 DEL 해 WRONGTYPE 충돌을 방지한다 (lifespan startup 용).

    키 `diconai:ws:alarms` 를 LIST→Stream 으로 재사용하므로, LIST→Stream 첫 배포 시
    옛 LIST 가 남아 있으면 XADD 가 WRONGTYPE 으로 실패한다. TYPE 이 `list` 일 때만
    DEL 하고, `stream`/`none` 이면 그대로 둔다 — 무조건 DEL 하면 매 재시작마다
    스트림이 wipe 된다. 예외는 삼켜 startup 을 막지 않는다 (loop 가 곧 재적재).
    """
    r = get_redis()
    try:
        key_type = await r.type(ALARM_QUEUE_KEY)
        if key_type == "list":
            await r.delete(ALARM_QUEUE_KEY)
            logger.info(
                "[alarm_queue] action=reset_legacy_list key=%s", ALARM_QUEUE_KEY
            )
    except Exception as exc:
        logger.warning(f"[alarm_queue] action=reset_stream_error error={exc!r}")


async def stream_tail_id() -> str | None:
    """스트림 말단(가장 최근) entry ID 를 반환한다 (stream lag 계산용).

    XREVRANGE key + - COUNT 1 로 마지막 1건의 ID 만 읽는다. 스트림이 비었거나
    예외면 None (호출자가 lag=0 처리).
    """
    r = get_redis()
    try:
        entries = await r.xrevrange(ALARM_QUEUE_KEY, count=1)
    except Exception:
        return None
    if not entries:
        return None
    return entries[0][0]  # (entry_id, fields) 의 entry_id


def _id_ms(stream_id: str) -> int:
    """스트림 entry ID `"<ms>-<seq>"` 의 ms 부분을 파싱한다 (lag 시간차 계산용)."""
    return int(stream_id.split("-")[0])
