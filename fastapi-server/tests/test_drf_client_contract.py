"""post_to_drf 실패 정책(raise_on_error)·timeout·DRF 다운 복원력 회귀 가드 (P0 신규).

[계약] (drf_client.py L73-146)
- raise_on_error=True  : 통신오류/timeout/4xx/5xx → DrfClientError
                         (가스: 센서에 4xx/5xx 응답이 필요하므로 예외로 전파)
- raise_on_error=False : 통신오류/timeout → None, 4xx/5xx → 응답 그대로 반환(예외 없음)
                         (전력/위치 fire-and-forget — DRF 가 죽어도 수신 흐름 비차단)
- timeout 인자          : 명시 시 그 값으로 httpx.AsyncClient 생성
                         (anomaly forward 등 fire-and-forget 은 2초로 단축해 빠른 실패)
"""

from unittest.mock import patch

import httpx
import pytest

from services import drf_client
from services.drf_client import DrfClientError, post_to_drf


class _Resp:
    """httpx.Response 스텁 — post_to_drf 가 읽는 status_code/text 만 보유."""

    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def _client_factory(*, post_result=None, post_exc=None, captured=None):
    """httpx.AsyncClient 대체 팩토리. post 가 post_result 반환 또는 post_exc 발생."""

    class _Client:
        def __init__(self, *args, **kwargs):
            # 최초 생성(메인 POST)의 timeout 만 캡처 — 후속 IntegrationLog 생성에 오염 방지.
            if captured is not None and "timeout" not in captured:
                captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            if post_exc is not None:
                raise post_exc
            return post_result

    return _Client


@pytest.mark.asyncio
async def test_connect_error_raises_when_raise_on_error_true():
    """DRF 연결 불가 + raise_on_error=True → DrfClientError(status=None)."""
    factory = _client_factory(post_exc=httpx.ConnectError("down"))
    with patch("httpx.AsyncClient", factory):
        with pytest.raises(DrfClientError) as ei:
            await post_to_drf("/api/monitoring/gas/", {}, raise_on_error=True)
    assert ei.value.status is None


@pytest.mark.asyncio
async def test_connect_error_returns_none_when_fire_and_forget():
    """DRF 연결 불가 + raise_on_error=False → None (수신 흐름 비차단)."""
    factory = _client_factory(post_exc=httpx.ConnectError("down"))
    with patch("httpx.AsyncClient", factory):
        res = await post_to_drf("/api/monitoring/power/", {}, raise_on_error=False)
    assert res is None


@pytest.mark.asyncio
async def test_timeout_raises_when_raise_on_error_true():
    """DRF 응답 timeout + raise_on_error=True → DrfClientError."""
    factory = _client_factory(post_exc=httpx.TimeoutException("slow"))
    with patch("httpx.AsyncClient", factory):
        with pytest.raises(DrfClientError):
            await post_to_drf("/api/monitoring/gas/", {}, raise_on_error=True)


@pytest.mark.asyncio
async def test_5xx_raises_with_status_when_raise_on_error_true():
    """DRF 5xx 응답 + raise_on_error=True → DrfClientError(status=500)."""
    factory = _client_factory(post_result=_Resp(500, "boom"))
    with patch("httpx.AsyncClient", factory):
        with pytest.raises(DrfClientError) as ei:
            await post_to_drf("/api/monitoring/gas/", {}, raise_on_error=True)
    assert ei.value.status == 500


@pytest.mark.asyncio
async def test_4xx_returns_response_when_fire_and_forget():
    """DRF 4xx 응답 + raise_on_error=False → 예외 없이 응답 그대로 반환(None 아님)."""
    factory = _client_factory(post_result=_Resp(404, "nope"))
    with patch("httpx.AsyncClient", factory):
        res = await post_to_drf("/api/monitoring/power/", {}, raise_on_error=False)
    assert res is not None and res.status_code == 404


@pytest.mark.asyncio
async def test_explicit_timeout_passed_to_httpx_client():
    """timeout 인자 명시 → 그 값으로 httpx.AsyncClient 생성 (fire-and-forget 단축)."""
    captured: dict = {}
    factory = _client_factory(post_result=_Resp(200), captured=captured)

    async def _noop(**kwargs):
        return None

    with (
        patch("httpx.AsyncClient", factory),
        patch.object(drf_client, "_record_integration_log", _noop),
    ):
        await post_to_drf("/api/monitoring/power/", {}, raise_on_error=False, timeout=2)
    assert captured["timeout"] == 2
