"""
어드민 패널 공용 페이지네이션.

응답 봉투 표준 5키({results, total, page, page_size, has_next})를 보장한다.
docs/api_response_convention.md 참조.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class AdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"

    def get_paginated_response(self, data):
        return Response(
            {
                "results": data,
                "total": self.page.paginator.count,
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "has_next": self.page.has_next(),
            }
        )
