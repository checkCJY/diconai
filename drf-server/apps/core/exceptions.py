"""DRF 전역 예외 핸들러.

응답 봉투 표준(docs/api_response_convention.md)에 따라 4xx/5xx 응답을
{error: {code, message, details?}} 구조로 일원화한다.

settings.REST_FRAMEWORK["EXCEPTION_HANDLER"]에 등록되어 모든 APIView에서 호출된다.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

logger = logging.getLogger(__name__)

# DRF 예외 default_code → 응답 봉투 표준 code 매핑
_CODE_MAP = {
    "authentication_failed": "authentication_required",
    "not_authenticated": "authentication_required",
    "permission_denied": "permission_denied",
    "not_found": "not_found",
    "method_not_allowed": "method_not_allowed",
    "invalid": "validation_failed",
    "parse_error": "validation_failed",
    "throttled": "throttled",
    "unsupported_media_type": "validation_failed",
}

# HTTP status → 표준 code 폴백 (DRF default_code가 없는 경우)
_STATUS_FALLBACK = {
    status.HTTP_400_BAD_REQUEST: "validation_failed",
    status.HTTP_401_UNAUTHORIZED: "authentication_required",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_429_TOO_MANY_REQUESTS: "throttled",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
    status.HTTP_502_BAD_GATEWAY: "upstream_unavailable",
    status.HTTP_503_SERVICE_UNAVAILABLE: "upstream_unavailable",
}


def _resolve_code(exc, status_code) -> str:
    drf_code = getattr(exc, "default_code", None)
    if drf_code and drf_code in _CODE_MAP:
        return _CODE_MAP[drf_code]
    return _STATUS_FALLBACK.get(status_code, "internal_error")


def _resolve_message(data, exc) -> str:
    """DRF 응답 데이터에서 사람이 읽을 한 줄 메시지 추출."""
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        # 첫 번째 검증 오류를 대표 메시지로
        for value in data.values():
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str):
                return value
    if isinstance(data, list) and data:
        return str(data[0])
    return getattr(exc, "default_detail", "요청 처리 중 오류가 발생했습니다.")


def _resolve_details(data):
    """필드 단위 검증 오류는 details로 노출. detail 단일 키는 노출 안 함."""
    if isinstance(data, dict) and "detail" not in data:
        return data
    return None


def standard_exception_handler(exc, context):
    """DRF가 처리 가능한 예외는 표준 봉투로 변환, 그 외는 500 표준 응답."""
    response = drf_default_handler(exc, context)

    if response is not None:
        code = _resolve_code(exc, response.status_code)
        message = _resolve_message(response.data, exc)
        body = {"error": {"code": code, "message": message}}
        details = _resolve_details(response.data)
        if details is not None:
            body["error"]["details"] = details
        response.data = body
        return response

    # DRF가 처리 못한 예외는 logging.error + 500 표준 응답
    view = context.get("view")
    logger.exception(
        "[unhandled] view=%s exc=%r",
        view.__class__.__name__ if view else "?",
        exc,
    )
    return Response(
        {
            "error": {
                "code": "internal_error",
                "message": "서버 내부 오류가 발생했습니다.",
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
