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
        from prometheus_client import CollectorRegistry
        from prometheus_client.multiprocess import MultiProcessCollector
        registry = CollectorRegistry()
        base = os.path.dirname(os.environ["PROMETHEUS_MULTIPROC_DIR"])
        for subdir in ("drf", "celery"):
            path = os.path.join(base, subdir)
            if os.path.isdir(path):
                MultiProcessCollector(registry, path=path)
        return HttpResponse(generate_latest(registry), content_type=CONTENT_TYPE_LATEST)
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
