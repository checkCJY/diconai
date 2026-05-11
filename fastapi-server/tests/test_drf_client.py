"""
drf_client 재귀 가드 스모크 테스트 (PR-F).

[회귀 커버]
- INTEGRATION_LOG_PATH 자체 호출 시 IntegrationLog 기록 안 함 (재귀 회피)
- _record_integration_log fire-and-forget — 실패해도 silent
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.drf_client import (
    INTEGRATION_LOG_PATH,
    _record_integration_log,
    post_to_drf,
)


@pytest.mark.asyncio
async def test_record_integration_log_silent_on_failure():
    """fire-and-forget — httpx 예외 시 silent (호출자 비차단)."""
    with patch("services.drf_client.httpx.AsyncClient") as mock_client:
        # post가 항상 실패
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=Exception("connection refused")
        )
        # 예외 발생하지 않고 silent 반환
        await _record_integration_log(
            integration_type="transmit",
            target_system="FastAPI→DRF",
            result="failure",
        )


@pytest.mark.asyncio
async def test_post_to_drf_skips_integration_log_for_self_path():
    """INTEGRATION_LOG_PATH 자체 호출은 IntegrationLog 기록 skip (재귀 회피)."""
    fake_response = type("R", (), {"status_code": 201, "text": ""})()

    with patch("services.drf_client.httpx.AsyncClient") as mock_client, patch(
        "services.drf_client._record_integration_log", new=AsyncMock()
    ) as mock_record:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=fake_response
        )
        await post_to_drf(INTEGRATION_LOG_PATH, json={"x": 1})
        mock_record.assert_not_called()


@pytest.mark.asyncio
async def test_post_to_drf_records_integration_log_for_normal_path():
    """일반 경로 호출은 IntegrationLog 기록 발생."""
    fake_response = type("R", (), {"status_code": 201, "text": ""})()

    with patch("services.drf_client.httpx.AsyncClient") as mock_client, patch(
        "services.drf_client._record_integration_log", new=AsyncMock()
    ) as mock_record:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=fake_response
        )
        await post_to_drf("/api/monitoring/gas/", json={"x": 1})
        mock_record.assert_called_once()
