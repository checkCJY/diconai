import os

from celery import Celery
from celery.signals import worker_process_shutdown

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("diconai")

# CELERY_ 네임스페이스로 settings.py에서 설정을 읽는다.
app.config_from_object("django.conf:settings", namespace="CELERY")

# INSTALLED_APPS의 모든 앱에서 tasks.py를 자동 탐색한다.
app.autodiscover_tasks()


@worker_process_shutdown.connect
def cleanup_prometheus_multiproc(pid, exitcode, **kwargs):
    # Celery 워커 프로세스 종료 시 해당 PID의 .db 파일을 즉시 정리한다.
    # gunicorn child_exit 훅과 동일한 목적 — stale 파일 누적 및 중복 집계 방지.
    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        from prometheus_client import multiprocess
        multiprocess.mark_process_dead(pid)
