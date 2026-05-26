"""HTTP 요청 메트릭 노출 — django-prometheus 패키지 의존 없이 동작.

django-prometheus가 django<6 요구라 직접 작성. fastapi-server/app.py의
prometheus 미들웨어와 메트릭 이름·label 동일하게 맞춤(서버 구분은 prometheus
scrape job label로).

multiprocess 모드:
  PROMETHEUS_MULTIPROC_DIR 환경변수가 설정되면 prometheus_client가 각 프로세스
  (gunicorn 워커, celery-worker)의 메트릭을 해당 디렉토리에 파일로 저장한다.
  /metrics 엔드포인트에서 MultiProcessCollector로 전체 파일을 합산해 노출하므로
  Celery 태스크에서 inc()한 Counter도 Prometheus가 수집할 수 있다.
"""

import os
import time

from django.http import HttpResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)


_HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
_HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)


class PrometheusMiddleware:
    """method/path/status 카운트 + duration 히스토그램.

    path는 resolver_match.route 사용 — `/api/users/<int:id>/` 처럼 라우트 패턴.
    매칭 실패(404) 시 raw path. /metrics 자체는 메트릭에서 제외.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/metrics":
            return self.get_response(request)
        start = time.perf_counter()
        response = self.get_response(request)
        elapsed = time.perf_counter() - start
        match = getattr(request, "resolver_match", None)
        path = getattr(match, "route", None) or request.path
        _HTTP_REQUESTS_TOTAL.labels(request.method, path, response.status_code).inc()
        _HTTP_REQUEST_DURATION.labels(request.method, path).observe(elapsed)
        return response


def metrics_view(_request):
    # PROMETHEUS_MULTIPROC_DIR 설정 시 모든 프로세스의 메트릭을 합산해 반환.
    # drf/celery 컨테이너가 서브디렉토리를 분리해 사용하므로 두 경로를 모두 집계한다.
    # 미설정(로컬 단독 실행) 시 기존 단일 프로세스 방식으로 동작.
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        import shutil
        import tempfile
        from prometheus_client import CollectorRegistry
        from prometheus_client.multiprocess import MultiProcessCollector

        base = os.path.dirname(os.environ["PROMETHEUS_MULTIPROC_DIR"])

        # 이성현 수정 — Celery 큐 분리에 따라 합산 경로 업데이트
        # celery 단일 워커 → celery-alarm / celery-metric 두 워커로 분리됨
        # 각 워커의 메트릭 파일이 다른 서브디렉토리에 저장되므로 두 경로 모두 합산 필요
        # PID 오프셋: drf=0, celery-alarm=100000, celery-metric=200000
        # 컨테이너 PID는 65535 이하이므로 오프셋 100000 간격으로 충돌 없음
        pid_offsets = {"drf": 0, "celery-alarm": 100_000, "celery-metric": 200_000}
        with tempfile.TemporaryDirectory() as tmpdir:
            for subdir, offset in pid_offsets.items():
                subpath = os.path.join(base, subdir)
                if not os.path.isdir(subpath):
                    continue
                for fname in os.listdir(subpath):
                    if not fname.endswith(".db"):
                        continue
                    # 파일명 끝 숫자(PID)에 오프셋을 더해 충돌 방지.
                    # 형식: {type}_{pid}.db 또는 {type}_{mode}_{pid}.db
                    stem, pid_str = fname[:-3].rsplit("_", 1)
                    new_name = (
                        f"{stem}_{int(pid_str) + offset}.db"
                        if pid_str.isdigit()
                        else fname
                    )
                    shutil.copy2(
                        os.path.join(subpath, fname), os.path.join(tmpdir, new_name)
                    )

            registry = CollectorRegistry()
            MultiProcessCollector(registry, path=tmpdir)
            return HttpResponse(
                generate_latest(registry), content_type=CONTENT_TYPE_LATEST
            )
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
