"""미등록 가스 센서 404 매핑 회귀 가드 (P1 신규).

#114 비동기 저장에서 누락됐다 복원된 미등록 센서 검증(gas_service.py L315-352):
Redis 등록 Set 미스 → 동기 저장으로 fallback → DRF 응답을 HTTP 상태로 매핑.
- DRF 400/404 (미등록 장치) → HTTP 404
- DRF 연결 불가(status None) → HTTP 503
등록된 센서는 fire-and-forget(asyncio.create_task)라 이 동기 경로를 타지 않는다.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import app
from services.drf_client import DrfClientError

client = TestClient(app)


class _FakeRedis:
    """sismember 항상 False(미등록) — 동기 fallback 경로 강제."""

    async def sismember(self, *args):
        return False

    async def sadd(self, *args):
        return 1


def _unregistered_gas() -> dict:
    return {
        "timestamp": "2026-06-15T00:00:00Z",
        "device_id": "UNREG-TEST-DEVICE",
        "device_name": "00:00:00:00:00:00",
        "location": {"x": 1.0, "y": 2.0},
        "o2": 20.9,
        "co": 0,
        "co2": 400,
        "h2s": 0,
        "lel": 0,
        "no2": 0,
        "so2": 0,
        "o3": 0,
        "nh3": 0,
        "voc": 0,
    }


def test_unregistered_sensor_maps_drf_400_to_404():
    """미등록 센서 + DRF 400(미등록 장치) → HTTP 404."""
    with (
        patch("gas.services.gas_service.get_redis", return_value=_FakeRedis()),
        patch(
            "gas.services.gas_service.post_to_drf",
            new=AsyncMock(side_effect=DrfClientError(400, "등록되지 않은 센서")),
        ),
    ):
        res = client.post("/api/sensors/gas", json=_unregistered_gas())
    assert res.status_code == 404


def test_unregistered_sensor_drf_unreachable_maps_to_503():
    """미등록 센서 + DRF 연결 불가(status None) → HTTP 503."""
    with (
        patch("gas.services.gas_service.get_redis", return_value=_FakeRedis()),
        patch(
            "gas.services.gas_service.post_to_drf",
            new=AsyncMock(side_effect=DrfClientError(None, "DRF 연결 불가")),
        ),
    ):
        res = client.post("/api/sensors/gas", json=_unregistered_gas())
    assert res.status_code == 503
