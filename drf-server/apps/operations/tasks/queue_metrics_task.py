# apps/operations/tasks/queue_metrics_task.py — Celery Beat: 큐 길이 메트릭 수집
#
# settings.py CELERY_BEAT_SCHEDULE에 등록되어 30초마다 실행된다.
# Redis LLEN 명령으로 Celery 큐에 쌓인 태스크 수를 읽어 CELERY_QUEUE_LENGTH Gauge에 기록.
#
# ── 왜 Beat 태스크인가 ──────────────────────────────────────────────────────
# Gauge는 "지금 이 순간의 상태값" — 이벤트 발생 시 inc()하는 Counter와 다르다.
# 큐 길이는 Redis에 있는 값을 주기적으로 폴링해야 한다.
# Beat가 단일 프로세스로 실행되므로 Gauge 중복 갱신 없이 정확한 현재값을 유지한다.
#
# ── 수집 주기: 30초 ─────────────────────────────────────────────────────────
# Prometheus scrape 기본 주기(15초)보다 길면 scrape 시점에 오래된 값이 노출된다.
# 30초는 scrape 2번에 1번 갱신 — "실시간성"보다 "DB/네트워크 부하 최소화"를 우선.
# 운영에서 더 세밀한 추적이 필요하면 crontab(*/15초)으로 줄일 수 있다.
# (crontab은 1분 단위라 30초는 schedule=timedelta(seconds=30) 형식 사용)
import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(name="apps.operations.tasks.queue_metrics_task.record_celery_queue_length")
def record_celery_queue_length():
    """
    Redis LLEN으로 Celery 큐 길이를 읽어 CELERY_QUEUE_LENGTH Gauge에 기록한다.

    큐 이름별로 측정하므로 나중에 도메인 전용 큐(alarm, position 등)를 추가해도
    queues 리스트만 늘리면 된다.
    """
    # 지연 import: 태스크 등록(import) 시점에 Redis 연결이 필요 없도록 한다.
    # Django 앱 초기화 완료 후 실행 시점에 연결 → startup 순서 충돌 방지.
    import redis

    from apps.core.metrics import CELERY_QUEUE_LENGTH

    # CELERY_BROKER_URL == REDIS_URL이므로 동일한 Redis 인스턴스에 접근.
    # Celery는 태스크를 Redis list에 직렬화해 저장하며, 키 이름이 큐 이름과 동일하다.
    try:
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)

        # 모니터링 대상 큐 목록.
        # 현재는 기본 큐("celery") 하나만 사용 중.
        # 도메인별 전용 큐를 만들면 여기에 추가한다 (예: "alarm", "position").

        # 이성현 수정 — Celery 큐 분리에 따라 모니터링 대상 큐 업데이트
        queues = ["alarm", "metric"]

        for queue_name in queues:
            length = r.llen(queue_name)
            CELERY_QUEUE_LENGTH.labels(queue=queue_name).set(length)

            if length > 50:
                # 50건 이상이면 worker가 태스크를 소화하지 못하는 상황.
                # Grafana에서도 alert를 설정해 두는 것이 권장되지만,
                # 로그도 남겨 celery worker 로그에서 직접 확인 가능하게 한다.
                logger.warning(
                    "[queue_metrics] queue='%s' backlog=%d (>50: worker overload suspected)",
                    queue_name,
                    length,
                )

    except Exception as e:
        # Redis 연결 실패 시 메트릭 수집을 건너뛰되 태스크 자체는 정상 종료.
        # 메트릭 수집 실패가 알람 처리 등 본 서비스 흐름에 영향을 주면 안 된다.
        logger.error("[queue_metrics] Redis 연결 실패, 큐 길이 수집 생략: %s", e)
