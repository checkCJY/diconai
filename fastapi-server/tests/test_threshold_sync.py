"""T4 D1b — DRF threshold-meta 5분 sync 캐시 검증.

[검증 대상]
- refresh_threshold_meta — DRF 응답으로 모듈 캐시 갱신
- get_threshold_meta / get_all_threshold_meta — 캐시 read
- fetch 실패 시 직전 캐시 유지 (운영 중단 회피)
- HTTP/JSON 예외 분기 silent fail
- threshold_sync_loop — 성공 시 5분 sleep, 실패 시 지수 backoff (단위 테스트는
  loop 자체 대신 refresh 의 반환값 흐름만)

[mock 패턴]
httpx.AsyncClient 를 patch — channel_meta_cache 의 동일 패턴 차용.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from power.services import threshold_sync


@pytest.fixture(autouse=True)
def reset_cache():
    """각 테스트 전 모듈 캐시 초기화 — 테스트 간 격리."""
    threshold_sync._threshold_meta.clear()
    yield
    threshold_sync._threshold_meta.clear()


@pytest.mark.asyncio
async def test_refresh_populates_cache_from_drf_response():
    """정상 응답 — 3개 item dict 가 모듈 캐시에 들어감."""
    drf_payload = {
        "power_w": {
            "warning_min": None,
            "warning_max": 80.0,
            "danger_min": None,
            "danger_max": 100.0,
            "unit": "%",
        },
        "current": {
            "warning_min": None,
            "warning_max": 80.0,
            "danger_min": None,
            "danger_max": 100.0,
            "unit": "%",
        },
        "voltage": {
            "warning_min": 95.0,
            "warning_max": 105.0,
            "danger_min": 90.0,
            "danger_max": 110.0,
            "unit": "%",
        },
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=drf_payload)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "power.services.threshold_sync.httpx.AsyncClient", return_value=mock_client
    ):
        ok = await threshold_sync.refresh_threshold_meta()

    assert ok is True
    assert threshold_sync.get_threshold_meta("power_w")["warning_max"] == 80.0
    assert threshold_sync.get_threshold_meta("voltage")["danger_min"] == 90.0
    assert set(threshold_sync.get_all_threshold_meta().keys()) == {
        "power_w",
        "current",
        "voltage",
    }


@pytest.mark.asyncio
async def test_refresh_returns_false_on_http_error_and_keeps_cache():
    """fetch 실패 — 직전 캐시 유지 (운영 중단 회피)."""
    # 사전 캐시 — 직전 sync 가 성공했었다는 가정
    threshold_sync._threshold_meta["power_w"] = {
        "warning_max": 80.0,
        "danger_max": 100.0,
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("drf down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "power.services.threshold_sync.httpx.AsyncClient", return_value=mock_client
    ):
        ok = await threshold_sync.refresh_threshold_meta()

    assert ok is False
    # 캐시 보존 — 실패가 clear 호출로 이어지면 알람 판정이 갑자기 NORMAL 폴백
    assert threshold_sync.get_threshold_meta("power_w")["warning_max"] == 80.0


@pytest.mark.asyncio
async def test_refresh_returns_false_on_json_decode_error():
    """JSON 파싱 실패 — silent False, 캐시 미변경."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(side_effect=ValueError("invalid json"))

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "power.services.threshold_sync.httpx.AsyncClient", return_value=mock_client
    ):
        ok = await threshold_sync.refresh_threshold_meta()

    assert ok is False
    assert threshold_sync.get_all_threshold_meta() == {}


@pytest.mark.asyncio
async def test_refresh_clears_stale_items_when_drf_removes_one():
    """DRF 응답에서 사라진 item 은 캐시에서도 사라짐 — clear + update 패턴."""
    threshold_sync._threshold_meta["power_w"] = {"warning_max": 80.0}
    threshold_sync._threshold_meta["current"] = {"warning_max": 80.0}

    # 새 응답에는 power_w 만
    drf_payload = {
        "power_w": {
            "warning_min": None,
            "warning_max": 75.0,
            "danger_min": None,
            "danger_max": 95.0,
            "unit": "%",
        }
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=drf_payload)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "power.services.threshold_sync.httpx.AsyncClient", return_value=mock_client
    ):
        await threshold_sync.refresh_threshold_meta()

    assert "current" not in threshold_sync.get_all_threshold_meta()
    assert threshold_sync.get_threshold_meta("power_w")["warning_max"] == 75.0


def test_get_threshold_meta_returns_empty_dict_when_missing():
    """캐시 미존재 item 은 빈 dict — decide_alarm 이 fail-safe NORMAL 처리."""
    assert threshold_sync.get_threshold_meta("nonexistent") == {}


def test_get_all_threshold_meta_returns_copy():
    """get_all 은 얕은 copy — 외부에서 수정해도 모듈 캐시 비손상."""
    threshold_sync._threshold_meta["power_w"] = {"warning_max": 80.0}
    snapshot = threshold_sync.get_all_threshold_meta()
    snapshot["power_w"]["warning_max"] = 999.0
    # 원본 dict 도 같이 변하긴 하지만 (얕은 copy 라 nested dict 는 공유) 최상위
    # 키 추가/삭제는 격리됨
    snapshot["new_item"] = {}
    assert "new_item" not in threshold_sync._threshold_meta
