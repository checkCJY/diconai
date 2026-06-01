"""services/drf_client.py — fastapi → DRF 호출 공용 클라이언트.

데이터 흐름:
  IN  : 각 도메인 service 의 POST 요청 (path + json payload)
  OUT : 1) DRF 로 httpx POST — 성공 시 Response, 실패 정책은 raise_on_error 로 분기
        2) /api/internal/integration-logs/ 로 연동 결과 1건 fire-and-forget 기록

gas/power/positioning service 의 중복 httpx POST 로직을 일원화한다.
- 공통 timeout: settings.DRF_REQUEST_TIMEOUT_SEC
- 공통 헤더: DRF_SERVICE_TOKEN 설정 시 Authorization 부착
- raise_on_error 로 실패 정책 선택:
    True  → 통신 오류/4xx/5xx 시 DrfClientError (gas: 센서에 4xx/5xx 응답 필요)
    False → 실패해도 None 반환, 호출자가 후속 흐름 계속 (power/positioning fire-and-forget)
어떤 경우든 실패는 logger.warning/error 로 남긴다.

IntegrationLog: 호출 결과를 비차단 기록(silent fail) — 실패해도 본 흐름에 영향 0.
재귀 회피를 위해 INTEGRATION_LOG_PATH 호출 자체는 기록하지 않는다.
"""

import logging

import httpx

from core.config import settings
from core.metrics import DRF_CALL_FAILED_TOTAL

logger = logging.getLogger(__name__)

INTEGRATION_LOG_PATH = "/api/internal/integration-logs/"


class DrfClientError(Exception):
    """DRF 호출 실패. 호출자가 raise_on_error=True일 때 발생."""

    def __init__(self, status: int | None, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _auth_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if settings.DRF_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {settings.DRF_SERVICE_TOKEN}"
    return headers


async def _record_integration_log(
    *,
    integration_type: str,
    target_system: str,
    result: str,
    description: str = "",
) -> None:
    """fire-and-forget IntegrationLog 기록. 실패해도 silent."""
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            await client.post(
                f"{settings.DRF_BASE_URL}{INTEGRATION_LOG_PATH}",
                json={
                    "integration_type": integration_type,
                    "target_system": target_system,
                    "result": result,
                    "description": description,
                },
                headers=_auth_headers(),  # 이성현 추가 — 토큰 헤더 추가
            )
    except Exception:
        # silent fail — 본 흐름 비차단. AppLog에 기록하면 또 재귀 위험.
        pass


async def post_to_drf(
    path: str,
    json: dict | list,
    *,
    raise_on_error: bool = False,
    log_category: str = "drf_client",
    timeout: float | None = None,
) -> httpx.Response | None:
    """DRF에 비동기 POST. 절대 URL 또는 상대 path를 받는다.

    Args:
        path: "/api/monitoring/gas/" 또는 "http://..." (절대)
        json: 직렬화 대상
        raise_on_error: 통신/4xx/5xx 시 DrfClientError 발생 여부
        log_category: 로깅 카테고리 (호출자가 도메인 식별 가능하도록)
        timeout: 호출별 timeout 초. None 이면 settings.DRF_REQUEST_TIMEOUT_SEC
            (기본 5초). anomaly forward 처럼 fire-and-forget 호출은 2초로 단축해
            빠른 실패 후 다음 inference 처리.

    Returns:
        성공 시 httpx.Response. raise_on_error=False에서 실패 시 None.
    """
    url = path if path.startswith("http") else f"{settings.DRF_BASE_URL}{path}"
    effective_timeout = (
        timeout if timeout is not None else settings.DRF_REQUEST_TIMEOUT_SEC
    )

    try:
        async with httpx.AsyncClient(timeout=effective_timeout) as client:
            res = await client.post(url, json=json, headers=_auth_headers())
    except httpx.ConnectError as exc:
        logger.error(f"[{log_category}] action=connect_failed url={url} error={exc}")
        DRF_CALL_FAILED_TOTAL.labels(error_type="connect_error").inc()
        if raise_on_error:
            raise DrfClientError(None, "DRF 서버에 연결할 수 없습니다.") from exc
        return None
    except httpx.TimeoutException as exc:
        logger.error(f"[{log_category}] action=timeout url={url} error={exc}")
        DRF_CALL_FAILED_TOTAL.labels(error_type="timeout").inc()
        if raise_on_error:
            raise DrfClientError(None, "DRF 서버 응답 시간 초과.") from exc
        return None
    except httpx.HTTPError as exc:
        logger.error(f"[{log_category}] action=http_error url={url} error={exc}")
        DRF_CALL_FAILED_TOTAL.labels(error_type="http_error").inc()
        if raise_on_error:
            raise DrfClientError(None, f"DRF 통신 오류: {exc}") from exc
        return None

    if res.status_code >= 400:
        body_preview = res.text[:120] if res.text else ""
        logger.warning(
            f"[{log_category}] action=non_success status={res.status_code} body={body_preview!r}"
        )
        error_type = "http_5xx" if res.status_code >= 500 else "http_4xx"
        DRF_CALL_FAILED_TOTAL.labels(error_type=error_type).inc()
        if raise_on_error:
            raise DrfClientError(res.status_code, body_preview or "DRF 응답 오류")

    # IntegrationLog 기록 (재귀 회피: 본 엔드포인트는 제외)
    if path != INTEGRATION_LOG_PATH:
        integration_type = (
            "collect"
            if any(seg in path for seg in ("/monitoring/", "/positioning/"))
            else "transmit"
        )
        await _record_integration_log(
            integration_type=integration_type,
            target_system="FastAPI→DRF",
            result="success" if res.status_code < 400 else "failure",
            description=f"path={path} status={res.status_code}",
        )

    return res
