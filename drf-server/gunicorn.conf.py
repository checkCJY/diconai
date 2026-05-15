import os
from prometheus_client import multiprocess


def child_exit(server, worker):
    # gunicorn 워커가 종료될 때 해당 PID의 .db 파일을 즉시 정리한다.
    # 정리하지 않으면 stale 파일이 누적되다가 비정상 종료된 파일에서
    # MultiProcessCollector JSON 파싱 실패 → /metrics 500 이 발생한다.
    multiprocess.mark_process_dead(worker.pid)
