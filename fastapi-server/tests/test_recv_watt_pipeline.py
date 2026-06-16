"""recv_watt 수신 파이프라인 wiring·비차단 회귀 가드 (P1 신규).

recv_watt(power_router.py L151-177) 계약:
- watt 수신 시 AI 추론(process_anomaly_inference)을 실행한다 (전류/전압/onoff 는 미실행).
- DRF 영속화는 BackgroundTask(bg.add_task)로 등록 — 응답을 막지 않는다(fire-and-forget).
  추론은 inline await 라 추론 시간이 E2E 에 포함되지만, DRF 왕복은 수신 응답을 지연시키지 않는다.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)

_SLAVE_KEYS = [
    "slave01",
    "slave02",
    "slave11",
    "slave12",
    "slave21",
    "slave22",
    "slave31",
    "slave32",
    "slave41",
    "slave42",
    "slave51",
    "slave52",
    "slave61",
    "slave62",
    "slave71",
    "slave72",
]


def _valid_watt() -> dict:
    return {"device_id": "POW-TEST-1", **{k: 100.0 for k in _SLAVE_KEYS}}


def test_recv_watt_runs_ai_inference_and_defers_drf_forward():
    """watt 수신 → AI 추론 1회 호출 + DRF forward 는 BackgroundTask 로 실행, 201 반환."""
    with (
        patch("power.routers.power_router.update_power_state", new=AsyncMock()),
        patch(
            "power.routers.power_router.process_anomaly_inference", new=AsyncMock()
        ) as mock_ai,
        patch(
            "power.routers.power_router.post_power_to_drf", new=AsyncMock()
        ) as mock_drf,
    ):
        res = client.post("/api/power/watt", json=_valid_watt())

    assert res.status_code == 201
    # AI 추론이 watt 경로에서 실행됨
    mock_ai.assert_awaited_once()
    assert mock_ai.await_args.args[2] == "watt"  # data_type 인자
    # DRF forward 는 BackgroundTask — TestClient 가 응답 후 실행 (수신 비차단)
    mock_drf.assert_awaited_once()
