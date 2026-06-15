"""drf-spectacular postprocessing hooks.

OpenAPI 스키마 생성 후처리.

[add_error_envelope_responses]
모든 엔드포인트의 4xx/5xx 응답에 표준 에러 봉투(ErrorEnvelope) 본문 스키마를 주입한다.
글로벌 예외 핸들러(apps/core/exceptions.py)가 4xx/5xx 를 아래 구조로 일원화하므로,
Swagger 에 본문 형태가 보이도록 응답 content 가 비어 있는 경우에만 채운다.

    { "error": { "code": "...", "message": "...", "details"?: {...} } }

스키마(구조)는 ErrorEnvelope 컴포넌트 하나를 공유하되, 예시(example)는 응답
상태코드별로 다르게 붙인다 — 401 에 not_found 예시가 뜨는 혼동을 막기 위함.
exceptions.py 의 _STATUS_FALLBACK 코드 매핑과 동기화한다.

본문 스키마를 명시한 응답(예: @extend_schema(responses={400: SomeSerializer}))은
덮어쓰지 않는다 — 개별 정의 우선.
"""

# 표준 에러 봉투 컴포넌트 스키마 (apps/core/exceptions.py 와 동기화)
ERROR_ENVELOPE_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "표준 에러 코드 (예: not_found, authentication_required).",
                },
                "message": {
                    "type": "string",
                    "description": "사람이 읽을 한 줄 메시지.",
                },
                "details": {
                    "type": "object",
                    "nullable": True,
                    "additionalProperties": True,
                    "description": "필드 단위 검증 오류 (검증 실패 시에만 포함).",
                },
            },
            "required": ["code", "message"],
        }
    },
    "required": ["error"],
}

# 상태코드 → (표준 코드, 예시 메시지). exceptions.py _STATUS_FALLBACK 과 동기화.
_STATUS_EXAMPLE = {
    400: ("validation_failed", "요청 데이터 검증에 실패했습니다."),
    401: ("authentication_required", "인증이 필요합니다."),
    403: ("permission_denied", "이 작업을 수행할 권한이 없습니다."),
    404: ("not_found", "요청하신 리소스를 찾을 수 없습니다."),
    405: ("method_not_allowed", "허용되지 않은 메서드입니다."),
    409: ("conflict", "리소스 상태가 충돌합니다."),
    422: ("validation_failed", "요청 데이터 검증에 실패했습니다."),
    429: ("throttled", "요청이 너무 많습니다. 잠시 후 다시 시도하세요."),
    500: ("internal_error", "서버 내부 오류가 발생했습니다."),
    502: ("upstream_unavailable", "상위 서비스에 연결할 수 없습니다."),
    503: ("upstream_unavailable", "상위 서비스에 연결할 수 없습니다."),
    504: ("upstream_unavailable", "상위 서비스에 연결할 수 없습니다."),
}

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def _example_for(status_code: int) -> dict:
    """상태코드에 맞는 에러 봉투 예시 본문을 만든다."""
    code, message = _STATUS_EXAMPLE.get(
        status_code, ("internal_error", "오류가 발생했습니다.")
    )
    example = {"error": {"code": code, "message": message}}
    # 검증 오류는 details 필드 형태도 함께 보여 준다.
    if code == "validation_failed":
        example["error"]["details"] = {"field_name": ["이 필드는 필수 항목입니다."]}
    return example


def add_error_envelope_responses(result, generator, request, public):
    """4xx/5xx 응답에 ErrorEnvelope 본문 스키마 + 코드별 예시를 주입한다."""
    schemas = result.setdefault("components", {}).setdefault("schemas", {})
    schemas["ErrorEnvelope"] = ERROR_ENVELOPE_SCHEMA

    ref = {"$ref": "#/components/schemas/ErrorEnvelope"}

    for path_item in result.get("paths", {}).values():
        for method, operation in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            for code, response in operation.get("responses", {}).items():
                # 숫자 상태코드 중 400 이상만 대상
                if not (code.isdigit() and int(code) >= 400):
                    continue
                if not isinstance(response, dict):
                    continue
                content = response.setdefault("content", {})
                # 이미 본문 스키마가 정의된 경우 존중 — 비어 있을 때만 봉투 주입
                if "application/json" not in content:
                    content["application/json"] = {
                        "schema": ref,
                        "example": _example_for(int(code)),
                    }

    return result
