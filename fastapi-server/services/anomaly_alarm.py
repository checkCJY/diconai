"""AI 이상탐지 추론 결과의 DRF forward helper.

[T4 D2 변경]
push_alarm / mark_ai_recent 호출은 본 함수에서 제거 — 호출자 (power_service.
process_anomaly_inference) 가 decide_alarm 매트릭스 결정 후 직접 호출. 본 함수는
DRF 영속화만 담당:
  1. MLAnomalyResult forward — 추론 매번 (운영 추적용).
  2. AnomalyAlarmRecord forward — alarm_payload 있을 때 (decide_alarm fire 결정).

[설계 결정]
- ML → alarm 은 sequential (ml_id 의존). gather + return_exceptions 의 silent
  invisible 함정 회피.
- 모든 외부 호출 silent fail + Prometheus counter (stage label) + logger.exception.
- kill switch FORWARD_ANOMALY_TO_DRF=false 시 즉시 return.
- timeout=2.0 명시 — httpx default 5s 너무 길어 fire-and-forget 패턴에 부적합.

[T4 D2 이전 흐름 (참고)]
이전엔 본 함수가 push_alarm 도 발사 (a 경로) + mark_ai_recent 도 호출. AI 가 단일
결정자가 아닌 환경에선 fastapi 가 AI 알람만 직접 push 했고, DRF 측 룰 알람과
race 가능. D2 로 fastapi 가 매트릭스 단일 결정자가 되어 (a) 경로 자연 사라짐.
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

# 본 sprint plan §Open Questions #2: dev=true / prod=true 기본. DRF SQLite 부하
# 발견 시 false 로 즉시 disable. push 까지 비활성 (forward 만 끄면 화면 표시는
# 유지 + DB 저장만 제외 같은 분리 필요하면 후속 sprint 에서 별도 flag 도입).
FORWARD_ENABLED = os.getenv("FORWARD_ANOMALY_TO_DRF", "true").lower() == "true"

ML_PATH = "/api/ml/anomaly-results/"
# DRF alerts 앱 mount = /alerts/. 본 sprint C1 신규 endpoint.
ALARM_PATH = "/alerts/api/anomaly-alarm-records/"

# fire-and-forget 호출의 빠른 실패 보장. httpx default 5s 너무 길음.
FORWARD_TIMEOUT_SEC = 2.0


async def forward_inference_e2e(
    ml_payload: dict,
    alarm_payload: dict | None = None,
) -> None:
    """T4 D2 — ML forward (매번) + AlarmRecord forward (alarm_payload 있을 때).

    Flow:
      1. ML forward (await, ml_id 추출).
      2. alarm_payload 있으면 AlarmRecord forward (await, ml_id 포함).

    모든 외부 호출 silent fail + Prometheus counter + logger.exception.
    `FORWARD_ANOMALY_TO_DRF=false` 시 early return (kill switch).

    Args:
        ml_payload: POST /api/ml/anomaly-results/ body (추론 매번).
        alarm_payload: POST /alerts/api/anomaly-alarm-records/ body. None 이면
            ML forward 만. decide_alarm 결과 source=ai 일 때만 호출자가 전달.

    호출자 (D2 후 — power_service.process_anomaly_inference):
        asyncio.create_task(forward_inference_e2e(ml_p, alarm_p))
        # push_alarm 은 호출자가 직접. mark_ai_state/recent 도 호출자.
    """
    if not FORWARD_ENABLED:
        return

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
