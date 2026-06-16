"""alarm_flush_loop 커서 기반 재작성 단위 테스트 (Step 2).

[검증 대상]
- 클라이언트 있으면 XREAD 배치 payload 전부를 순회하며 각각 broadcast (엣지케이스 ①)
- 커서(last_id)가 배치 마지막 entry ID 로 전진
- stream lag 메트릭이 iteration 말미에 set
- [M-1] 클라이언트 없으면 XREAD 호출 안 함 + 커서 동결 (스트림에 알람 보존)
- ingress_ts 는 broadcast payload 에서 pop + E2E latency observe

[루프 탈출]
alarm_flush_loop 은 `while True` 무한 루프라, mock 의 side effect 로 sentinel 예외를
던져 원하는 iteration 직후 빠져나온다.
"""

from unittest.mock import Mock, patch

import pytest

from websocket.routers import ws_router


class _StopLoop(Exception):
    """테스트에서 무한 루프를 끊기 위한 sentinel."""


@pytest.mark.asyncio
async def test_flush_loop_broadcasts_batch_and_advances_cursor():
    """클라 있음 → XREAD 배치 2건 각각 broadcast, 커서 전진, lag set."""
    sent = []

    async def fake_send(payload):
        sent.append(payload)

    reads = [
        ("3-0", [{"risk_level": "danger", "n": 1}, {"risk_level": "warning", "n": 2}])
    ]

    async def fake_read(last_id, timeout):
        if reads:
            return reads.pop(0)
        raise _StopLoop  # 두 번째 iteration 진입 시 탈출

    async def fake_tail():
        return "3-0"

    async def fake_state():
        # 배치 broadcast 전 1회 조회되는 state — build_broadcast_payload 가 mock 이라 내용 무관.
        return {}

    lag_metric = Mock()
    with (
        patch.object(ws_router, "sensor_clients", [object()]),
        patch.object(ws_router, "read_alarms_blocking", fake_read),
        patch.object(ws_router, "_send_to_all", fake_send),
        patch.object(ws_router, "stream_tail_id", fake_tail),
        patch.object(ws_router, "fetch_broadcast_state", fake_state),
        patch.object(
            ws_router, "build_broadcast_payload", lambda state, include_alarms: {}
        ),
        patch.object(ws_router, "ALARM_STREAM_LAG", lag_metric),
    ):
        with pytest.raises(_StopLoop):
            await ws_router.alarm_flush_loop()

    # 배치 2건 → 2회 broadcast, 각 payload 는 alarms=[해당 1건]
    assert len(sent) == 2
    assert sent[0]["alarms"][0]["n"] == 1
    assert sent[1]["alarms"][0]["n"] == 2
    # tail==last_id=="3-0" → lag 0.0 set
    lag_metric.set.assert_called_with(0.0)


@pytest.mark.asyncio
async def test_flush_loop_freezes_cursor_when_no_clients():
    """[M-1] 클라 없음 → XREAD 미호출 + sleep 만, 커서 동결."""
    read_calls = []

    async def fake_read(last_id, timeout):
        read_calls.append(last_id)
        return ("$", [])

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        raise _StopLoop  # 첫 sleep 직후 탈출

    with (
        patch.object(ws_router, "sensor_clients", []),
        patch.object(ws_router, "read_alarms_blocking", fake_read),
        patch("asyncio.sleep", fake_sleep),
    ):
        with pytest.raises(_StopLoop):
            await ws_router.alarm_flush_loop()

    assert read_calls == []  # XREAD 호출 자체 안 함 — 커서 동결, 알람 보존
    assert sleeps == [1]


@pytest.mark.asyncio
async def test_flush_loop_pops_ingress_ts_and_observes_latency():
    """ingress_ts 는 broadcast 전에 pop + E2E latency 를 risk_level 라벨로 observe."""
    sent = []

    async def fake_send(payload):
        sent.append(payload)

    reads = [("1-0", [{"risk_level": "danger", "ingress_ts": 100.0}])]

    async def fake_read(last_id, timeout):
        if reads:
            return reads.pop(0)
        raise _StopLoop

    async def fake_tail():
        return "1-0"

    async def fake_state():
        return {}

    label_calls = []
    metric = Mock()
    metric.labels.side_effect = lambda **kw: (label_calls.append(kw), metric)[1]

    with (
        patch.object(ws_router, "sensor_clients", [object()]),
        patch.object(ws_router, "read_alarms_blocking", fake_read),
        patch.object(ws_router, "_send_to_all", fake_send),
        patch.object(ws_router, "stream_tail_id", fake_tail),
        patch.object(ws_router, "fetch_broadcast_state", fake_state),
        patch.object(
            ws_router, "build_broadcast_payload", lambda state, include_alarms: {}
        ),
        patch.object(ws_router, "E2E_ALARM_LATENCY", metric),
    ):
        with pytest.raises(_StopLoop):
            await ws_router.alarm_flush_loop()

    # ingress_ts 는 broadcast payload 에서 제거됨
    assert "ingress_ts" not in sent[0]["alarms"][0]
    # risk_level 라벨로 latency observe
    assert {"risk_level": "danger"} in label_calls
    metric.observe.assert_called_once()
