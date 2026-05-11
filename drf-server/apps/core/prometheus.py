"""HTTP 요청 메트릭 노출 — django-prometheus 패키지 의존 없이 동작.

django-prometheus가 django<6 요구라 직접 작성. fastapi-server/app.py의
prometheus 미들웨어와 메트릭 이름·label 동일하게 맞춤(서버 구분은 prometheus
scrape job label로).
"""

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
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
