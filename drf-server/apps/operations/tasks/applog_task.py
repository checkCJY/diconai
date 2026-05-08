"""
AppLog 비동기 INSERT Celery 태스크 (PR-D B-2).

[설계]
DBLogHandler.emit()이 본 태스크에 fire-and-forget delay() 호출.
Celery worker가 별도 프로세스에서 AppLog.objects.create() 실행 → web pod의 응답 latency
0 영향. broker(Redis) 다운 시 db_handler가 graceful fallback (동기 INSERT)으로 전환.

[Celery worker 동시성]
acks_late=False (default). worker 장애 시 메시지 손실 가능 — 로그용이라 acceptable.
운영 진입 후 critical 로그 손실 방지 필요 시 acks_late=True + retry 검토.

[재귀 가드]
DBLogHandler가 thread-local 가드로 중복 진입 차단. 본 태스크는 ORM만 호출하므로
재귀 위험 0 (logger 자기 호출 안 함).
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0, ignore_result=True)
def applog_create_task(
    self,
    log_category: str,
    service_module: str,
    level: str,
    message: str,
):
    """AppLog.objects.create()를 Celery worker 별도 프로세스에서 비동기 실행."""
    try:
        from apps.operations.models import AppLog

        AppLog.objects.create(
            log_category=log_category,
            service_module=service_module,
            level=level,
            message=message,
        )
    except Exception as exc:
        # silent fail — DBLogHandler가 stdout fallback. retry 0회 (로그 손실 허용).
        logger.warning("AppLog 비동기 INSERT 실패: %s", exc)
