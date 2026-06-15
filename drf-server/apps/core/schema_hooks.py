"""drf-spectacular postprocessing hooks.

OpenAPI 스키마 생성 후처리.

[add_error_envelope_responses]
모든 엔드포인트의 4xx/5xx 응답에 표준 에러 봉투(ErrorEnvelope) 본문 스키마를 주입한다.
글로벌 예외 핸들러(apps/core/exceptions.py)가 4xx/5xx 를 아래 구조로 일원화하므로,
Swagger 에 본문 형태가 보이도록 응답 content 가 비어 있는 경우에만 채운다.

    { "error": { "code": "...", "message": "...", "details"?: {...} } }

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
                    "example": "not_found",
                },
                "message": {
                    "type": "string",
                    "description": "사람이 읽을 한 줄 메시지.",
                    "example": "요청하신 리소스를 찾을 수 없습니다.",
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

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def add_error_envelope_responses(result, generator, request, public):
    """4xx/5xx 응답에 ErrorEnvelope 본문 스키마를 주입한다."""
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
                    content["application/json"] = {"schema": ref}

    return result
