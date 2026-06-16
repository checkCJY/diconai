"""_send_to_all 브로드캐스트 fan-out + 끊긴 클라 정리 회귀 가드 (P0 신규).

ws_router._send_to_all 은 sensor_clients 전원에 병렬(asyncio.gather)로 전송하고,
전송 실패한 클라이언트만 목록에서 제거한다(ws_router.py L41-54). 한 클라의 실패가
나머지 전송을 막지 않아야(fault isolation) 하며, 정상 클라는 목록에 유지돼야 한다.
이 계약이 깨지면 끊긴 소켓이 누적돼 broadcast 가 통째로 막히거나 예외로 죽는다.
"""

from unittest.mock import patch

import pytest

from websocket.routers import ws_router


class _FakeWS:
    """send_json 만 구현한 최소 WebSocket 스텁. fail=True 면 전송 시 예외."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent: list = []

    async def send_json(self, payload):
        if self.fail:
            raise RuntimeError("client disconnected")
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_send_to_all_broadcasts_to_every_client():
    """정상 클라 N개 전원에 동일 payload 1회씩 전송 + 목록 유지(제거 없음)."""
    clients = [_FakeWS() for _ in range(5)]
    payload = {"type": "alarm", "n": 1}
    with patch.object(ws_router, "sensor_clients", list(clients)):
        await ws_router._send_to_all(payload)
        for c in clients:
            assert c.sent == [payload]
        assert len(ws_router.sensor_clients) == 5


@pytest.mark.asyncio
async def test_send_to_all_removes_only_disconnected_clients():
    """끊긴 클라만 제거, 정상 클라는 유지+정상 수신(1개 실패가 나머지 전송 안 막음)."""
    ok1, bad, ok2 = _FakeWS(), _FakeWS(fail=True), _FakeWS()
    with patch.object(ws_router, "sensor_clients", [ok1, bad, ok2]):
        await ws_router._send_to_all({"x": 1})
        assert ok1.sent == [{"x": 1}]  # fault isolation
        assert ok2.sent == [{"x": 1}]
        assert bad not in ws_router.sensor_clients
        assert ws_router.sensor_clients == [ok1, ok2]


@pytest.mark.asyncio
async def test_send_to_all_empty_clients_is_noop():
    """클라 0명 → 예외 없이 즉시 반환 (빈 gather)."""
    with patch.object(ws_router, "sensor_clients", []):
        await ws_router._send_to_all({"x": 1})  # 예외가 나지 않으면 통과
