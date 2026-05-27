import os
import time

from celery import Celery
from celery.signals import (
    before_task_publish,
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    worker_process_shutdown,
)

# Celery 워커는 docker-compose에서 실행 → prod 설정 기본값
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

app = Celery("diconai")

# CELERY_ 네임스페이스로 settings.py에서 설정을 읽는다.
app.config_from_object("django.conf:settings", namespace="CELERY")

# INSTALLED_APPS의 모든 앱에서 tasks.py를 자동 탐색한다.
app.autodiscover_tasks()

# 태스크 실행 시작 시각을 task_id → float으로 임시 저장.
# task_prerun에서 기록하고 task_postrun에서 읽어서 제거한다.
# worker 프로세스별 메모리이므로 동시성 문제 없음.
_task_start_times: dict[str, float] = {}


@before_task_publish.connect
def on_task_publish(headers: dict, **kwargs):
    # 태스크가 큐에 들어가는 시점의 timestamp를 헤더에 심는다.
    # task_prerun에서 이 값을 읽어 대기시간(C2)을 계산한다.
    headers["enqueued_at"] = time.time()


@task_prerun.connect
def on_task_prerun(task_id: str, task, **kwargs):
    from apps.core.metrics import CELERY_TASK_QUEUED

    _task_start_times[task_id] = time.time()

    # 헤더에 enqueued_at이 있으면 대기시간 기록.
    # apply_async를 통하지 않은 직접 호출(task.apply())에는 헤더가 없으므로 skip.
    enqueued_at = (task.request.headers or {}).get("enqueued_at")
    if enqueued_at:
        CELERY_TASK_QUEUED.labels(task_name=task.name).observe(
            time.time() - enqueued_at
        )


@task_postrun.connect
def on_task_postrun(task_id: str, task, **kwargs):
    from apps.core.metrics import CELERY_TASK_DURATION

    start = _task_start_times.pop(task_id, None)
    if start is not None:
        CELERY_TASK_DURATION.labels(task_name=task.name).observe(time.time() - start)


@task_failure.connect
def on_task_failure(task_id: str, exception, **kwargs):
    # 태스크가 예외로 최종 실패했을 때 (재시도 없이 종료된 경우).
    # task_postrun은 성공/실패 구분 없이 호출되므로 이 시그널로 따로 카운트한다.
    from apps.core.metrics import CELERY_TASK_FAILED_TOTAL

    sender = kwargs.get("sender")
    task_name = getattr(sender, "name", "unknown")
    CELERY_TASK_FAILED_TOTAL.labels(task_name=task_name).inc()


@task_retry.connect
def on_task_retry(request, reason, **kwargs):
    # 태스크가 실패 후 재시도 큐에 들어갈 때 호출.
    # 재시도가 쌓이면 FastAPI 불안정 또는 DB 락 신호 — alarm_ws_push_failed_total과 함께 확인.
    from apps.core.metrics import CELERY_TASK_RETRIED_TOTAL

    task_name = getattr(request, "task", "unknown")
    CELERY_TASK_RETRIED_TOTAL.labels(task_name=task_name).inc()


@worker_process_shutdown.connect
def cleanup_prometheus_multiproc(pid, exitcode, **kwargs):
    # Celery 워커 프로세스 종료 시 해당 PID의 .db 파일을 즉시 정리한다.
    # gunicorn child_exit 훅과 동일한 목적 — stale 파일 누적 및 중복 집계 방지.
    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        from prometheus_client import multiprocess
        multiprocess.mark_process_dead(pid)
