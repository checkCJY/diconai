"""AI 이상탐지 추론 결과의 DRF forward helper.

[책임 범위]
push_alarm / mark_ai_recent 는 호출자 (power_service.process_anomaly_inference)
가 decide_alarm 매트릭스 결정 후 직접 호출한다. 본 함수는 DRF 영속화만 담당:
  1. MLAnomalyResult forward — 추론 매번 (운영 추적용).
  2. AnomalyAlarmRecord forward — alarm_payload 있을 때 (decide_alarm fire 결정).

[설계 결정]
- ML → alarm 은 sequential (ml_id 의존). gather + return_exceptions 의 silent
  invisible 함정 회피.
- 모든 외부 호출 silent fail + Prometheus counter (stage label) + logger.exception.
- kill switch FORWARD_ANOMALY_TO_DRF=false 시 즉시 return.
- timeout=2.0 명시 — httpx default 5s 너무 길어 fire-and-forget 패턴에 부적합.
"""

import logging
import os

from prometheus_client import Counter

from services.drf_client import post_to_drf

logger = logging.getLogger(__name__)

# Prometheus — 실패 원인 단계별 카운터 (ml | alarm | push).
# 운영 시 grafana 로 stage 별 추세 추적, kill switch 발동 판단 자료.
anomaly_forward_failures = Counter(
    "anomaly_forward_failures_total",
    "DRF anomaly forward 실패 횟수",
    ["stage"],
)

# kill switch — 기본 활성(dev/prod 모두 true). DRF SQLite 부하 발견 시 false 로
# 즉시 disable. forward·push 모두 비활성 (화면 표시 유지 + DB 저장만 제외 같은
# 분리가 필요하면 별도 flag 도입).
FORWARD_ENABLED = os.getenv("FORWARD_ANOMALY_TO_DRF", "true").lower() == "true"

ML_PATH = "/api/ml/anomaly-results/"
# DRF alerts 앱 mount = /alerts/. 본 sprint C1 신규 endpoint.
ALARM_PATH = "/alerts/api/anomaly-alarm-records/"

# fire-and-forget 호출의 빠른 실패 보장. httpx default 5s 너무 길음.
FORWARD_TIMEOUT_SEC = 2.0


async def forward_inference_e2e(
    ml_payload: dict,
    alarm_payload: dict | None = None,
) -> dict | None:
    """ML forward (매번) + AlarmRecord forward (alarm_payload 있을 때).

    Flow:
      1. ML forward (await, ml_id 추출).
      2. alarm_payload 있으면 AlarmRecord forward (await, ml_id 포함).

    Returns:
        alarm_payload 가 있고 DRF 가 201 응답 시 `{alarm_id, event_id}` 반환.
        그 외 (alarm_payload None / DRF fail / kill switch) None. 호출자가
        push 페이로드에 event_id 보강할 때 사용 (popup 격상/RESOLVED/상세보기/ack
        4가지 동작이 event_id 의존이라 — 본 응답 활용 안 하면 모두 동작 안 함).

    모든 외부 호출 silent fail + Prometheus counter + logger.exception.
    `FORWARD_ANOMALY_TO_DRF=false` 시 early return (kill switch).

    호출자 (power.services.anomaly_inference.process_anomaly_inference):
        - 정상 race: `await asyncio.wait_for(forward_inference_e2e(...), timeout=0.5)`
        - timeout 시: `asyncio.create_task(...)` 으로 background 위임
        push_alarm 은 호출자가 직접 (event_id 보강 후). mark_ai_state/recent 도 호출자.
    """
    if not FORWARD_ENABLED:
        return None

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

    if alarm_payload is None:
        return None

    # AlarmRecord forward — ml_id 없을 수도 있음 (ML forward 실패 시 None).
    # DRF view 의 ml_anomaly_result_id 는 optional 이라 None 그대로 전달 OK.
    try:
        alarm_response = await post_to_drf(
            ALARM_PATH,
            {**alarm_payload, "ml_anomaly_result_id": ml_id},
            raise_on_error=False,
            log_category="anomaly_forward_alarm",
            timeout=FORWARD_TIMEOUT_SEC,
        )
        if alarm_response is not None and alarm_response.status_code == 201:
            return alarm_response.json()
    except Exception:
        logger.exception("[anomaly_forward] alarm forward failed")
        anomaly_forward_failures.labels(stage="alarm").inc()

    return None
