"""AI 이상탐지 추론 결과의 DRF forward + WS push 공용 helper.

[목적]
power/gas service 가 IF 추론 후 호출. 3가지 외부 호출을 단일 task 안에 캡슐화:
  1. push_alarm — Redis 알람 큐 (브라우저 broadcast). ML 의존성 없음.
  2. MLAnomalyResult forward — 추론 매번 (운영 추적용).
  3. AnomalyAlarmRecord forward — 발화 시 (rate limit 통과 후). ml_id 의존.

[설계 결정 — 본 sprint plan 참고]
- push 는 ML 의존성 없음 → 독립 task 즉시 발사 (C12 효과 보존, push 가 ML latency
  /SQLite lock 에 묶이지 않음).
- ML → alarm 은 sequential (ml_id 의존). gather + return_exceptions 의 silent
  invisible 함정 회피.
- 모든 외부 호출 silent fail + Prometheus counter (stage label) + logger.exception.
- kill switch FORWARD_ANOMALY_TO_DRF=false 시 즉시 return (push 까지 모두 비활성).
- timeout=2.0 명시 — httpx default 5s 너무 길어 fire-and-forget 패턴에 부적합.

[호출자]
power/gas service 가 `asyncio.create_task(forward_inference_e2e(...))` 로 wrap.
helper 안에서 또 task 분기 → push 만 별도 task (ML await 전에 fire).
"""

import asyncio
import logging
import os

from prometheus_client import Counter

from core.constants import AI_TO_RULE_LEVEL
from services.ai_mute import mark_ai_recent
from services.drf_client import post_to_drf
from websocket.services.alarm_queue import push_alarm

logger = logging.getLogger(__name__)

# Prometheus — 실패 원인 단계별 카운터 (ml | alarm | push).
# 운영 시 grafana 로 stage 별 추세 추적, kill switch 발동 판단 자료.
anomaly_forward_failures = Counter(
    "anomaly_forward_failures_total",
    "DRF anomaly forward 실패 횟수",
    ["stage"],
)

# 본 sprint plan §Open Questions #2: dev=true / prod=true 기본. DRF SQLite 부하
# 발견 시 false 로 즉시 disable. push 까지 비활성 (forward 만 끄면 화면 표시는
# 유지 + DB 저장만 제외 같은 분리 필요하면 후속 sprint 에서 별도 flag 도입).
FORWARD_ENABLED = os.getenv("FORWARD_ANOMALY_TO_DRF", "true").lower() == "true"

ML_PATH = "/api/ml/anomaly-results/"
# DRF alerts 앱 mount = /alerts/. 본 sprint C1 신규 endpoint.
ALARM_PATH = "/alerts/api/anomaly-alarm-records/"

# fire-and-forget 호출의 빠른 실패 보장. httpx default 5s 너무 길음.
FORWARD_TIMEOUT_SEC = 2.0


async def _safe_push(push_payload: dict) -> None:
    """push_alarm fire-and-forget wrapper — silent fail + observable.

    asyncio.create_task 안 exception 이 외부로 안 나가므로 별도 wrap.
    Redis 일시 hang / 장애 시 fastapi 워커 안 묶음.
    """
    try:
        await push_alarm(push_payload)
    except Exception:
        logger.exception("[anomaly_forward] push_alarm failed")
        anomaly_forward_failures.labels(stage="push").inc()


async def forward_inference_e2e(
    ml_payload: dict,
    alarm_payload: dict,
    push_payload: dict,
    should_fire: bool,
) -> None:
    """추론 매번 ML forward + 발화 시 push 독립 + AlarmRecord forward (sequential).

    Flow:
      1. push_alarm 즉시 별도 task (ML 의존성 없음 — C12 효과 유지).
      2. ML forward (await, ml_id 추출).
      3. AlarmRecord forward (await, ml_id 포함).

    모든 외부 호출 silent fail + Prometheus counter + logger.exception.
    `FORWARD_ANOMALY_TO_DRF=false` 시 early return (kill switch, push 까지 비활성).

    Args:
        ml_payload: POST /api/ml/anomaly-results/ body (추론 매번).
        alarm_payload: POST /alerts/api/anomaly-alarm-records/ body. helper 가
            ml_anomaly_result_id 를 추가 주입.
        push_payload: Redis 큐로 보낼 dict. brower WS broadcast 용.
        should_fire: 발화 여부 (rate limit + combined_risk in FIRE_LEVELS).
            False 면 push/alarm 모두 skip, ML forward 만 (운영 추적).

    호출자 예시:
        asyncio.create_task(forward_inference_e2e(ml_p, alarm_p, push_p, fire))
    """
    if not FORWARD_ENABLED:
        return

    # push 는 ML 의존성 없음 → 독립 task 즉시 발사. C12 효과(ML latency 에 push 가
    # 묶이지 않음) 보존. push 실패는 _safe_push 안에서 silent + counter.
    if should_fire:
        # [Step 3] AI 발화 마킹 — DRF power_alarm 의 룰 fire 를 60s suppress.
        # push 와 같은 시점에 fire-and-forget. 마킹 실패는 silent (mark_ai_recent
        # 내부) — 마킹 실패 시 룰 가드 작동 안 해 중복 1건 노출되는 정도.
        meta = push_payload.get("anomaly_meta") or {}
        combined_risk = meta.get("combined_risk", "normal")
        rule_level = AI_TO_RULE_LEVEL.get(combined_risk, combined_risk)
        asyncio.create_task(
            mark_ai_recent(meta.get("device_id"), meta.get("channel"), rule_level)
        )
        asyncio.create_task(_safe_push(push_payload))

    # ML forward → ml_id 추출. silent fail (response None / status != 201).
    ml_id: int | None = None
    try:
        ml_response = await post_to_drf(
            ML_PATH,
            ml_payload,
            raise_on_error=False,
            log_category="anomaly_forward_ml",
            timeout=FORWARD_TIMEOUT_SEC,
        )
        if ml_response is not None and ml_response.status_code == 201:
            ml_id = ml_response.json().get("id")
    except Exception:
        logger.exception("[anomaly_forward] ML forward failed")
        anomaly_forward_failures.labels(stage="ml").inc()

    if not should_fire:
        return

    # AlarmRecord forward — ml_id 없을 수도 있음 (ML forward 실패 시 None).
    # DRF view 의 ml_anomaly_result_id 는 optional 이라 None 그대로 전달 OK.
    try:
        await post_to_drf(
            ALARM_PATH,
            {**alarm_payload, "ml_anomaly_result_id": ml_id},
            raise_on_error=False,
            log_category="anomaly_forward_alarm",
            timeout=FORWARD_TIMEOUT_SEC,
        )
    except Exception:
        logger.exception("[anomaly_forward] alarm forward failed")
        anomaly_forward_failures.labels(stage="alarm").inc()
