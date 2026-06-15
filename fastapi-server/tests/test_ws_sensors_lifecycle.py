"""/ws/sensors/ 연결 수명·인증 회귀 가드 (P1 신규).

sensor_stream 엔드포인트(ws_router.py L142-174):
- JWT 활성(JWT_SIGNING_KEY 설정) + 토큰 누락/무효 → 1008 close (미인증 거부)
- 인증 통과 → sensor_clients 등록, 연결 종료(finally) 시 반드시 정리
연결 정리가 깨지면 끊긴 소켓이 누적돼 broadcast fan-out 이 막힌다([[_send_to_all]]).
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import app
from websocket.routers import ws_router

client = TestClient(app)


def test_ws_sensors_rejects_when_token_missing(monkeypatch):
    """JWT 활성 + 토큰 누락 → 1008(unauthenticated)로 close."""
    monkeypatch.setattr("core.config.settings.JWT_SIGNING_KEY", "test-secret")
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/sensors/") as ws:
            ws.receive_text()
    assert exc.value.code == 1008


def test_ws_sensors_accept_and_disconnect_cleanup(monkeypatch):
    """인증 비활성 → 연결 시 sensor_clients 등록, 종료 시 정리(누수 0)."""
    monkeypatch.setattr("core.config.settings.JWT_SIGNING_KEY", "")
    before = len(ws_router.sensor_clients)

    async def fake_state():
        return {}

    with (
        patch.object(ws_router, "fetch_broadcast_state", fake_state),
        patch.object(
            ws_router, "build_broadcast_payload", lambda state, include_alarms: {}
        ),
    ):
        with client.websocket_connect("/ws/sensors/") as ws:
            ws.receive_json()  # 첫 payload 수신 → append 완료 보장
            assert len(ws_router.sensor_clients) == before + 1
        # with 종료 = disconnect → finally 에서 정리
        assert len(ws_router.sensor_clients) == before
