"""
IntegrationLog 비동기 INSERT Celery 태스크 (PR-D B-3).

[설계 변경 — plan §3 PR-D B-3 vs 본 구현]
plan §3 PR-D B-3는 "in-memory queue + 5초/10건 flush" 권장이었으나, in-memory queue는
K8s/Docker pod 재시작 시 데이터 손실 위험이 있어 PR-D B-2(AppLog Celery)와 동일 패턴
(Celery 큐 비동기 INSERT)으로 단순화. 효과는 동일 (web pod의 latency 0).

[본 태스크 호출처]
- DRF 내부: `apps/alerts/tasks.py::_push_to_ws()` — 알람 푸시 결과 기록
- fastapi 측은 이미 async BackgroundTask로 fire-and-forget — 변경 불필요. docstring만 갱신.

[broker fallback]
broker 다운 시 호출자에서 try/except로 silent fail. IntegrationLog 미기록은 운영 추적성
손실이지만 본 흐름(알람 푸시)은 비차단. 운영 진입 시 broker 가용성 모니터링 권장.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0, ignore_result=True)
def integration_log_create_task(
    self,
    integration_type: str,
    target_system: str,
    result: str,
    description: str = "",
):
    """IntegrationLog.objects.create()를 Celery worker에서 비동기 실행."""
    try:
        from apps.operations.models import IntegrationLog

        IntegrationLog.objects.create(
            integration_type=integration_type,
            target_system=target_system,
            result=result,
            description=description,
        )
    except Exception as exc:
        logger.warning("IntegrationLog 비동기 INSERT 실패: %s", exc)
