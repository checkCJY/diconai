"""services.anomaly_alarm.forward_inference_e2e 단위 테스트 (C2).

[검증 대상]
- 정상 — ML forward 201 → ml_id 캡처 → alarm forward (ml_id 포함)
- ML forward 실패 (response None) — ml_id=None, alarm forward 진행 (None 포함)
- should_fire=False — push/alarm skip, ML forward 만
- kill switch off (FORWARD_ANOMALY_TO_DRF=false) — 즉시 return, post_to_drf 0회
- push_alarm 독립성 — ML forward 가 hang 해도 push 는 그 전에 호출됨

[timing 주의]
helper 안 `asyncio.create_task(_safe_push(...))` 가 만든 task 는 fire-and-forget
이라 helper 종료 시점에 아직 실행 안 됐을 수 있음. 테스트에서 push 호출을 검증
하려면 `await asyncio.sleep(0)` (또는 finer) 로 event loop 한 turn 양보 필요.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from services import anomaly_alarm


@pytest.fixture
def payloads():
    return {
        "ml": {"sensor_type": "power", "anomaly_score": -0.07},
        "alarm": {"alarm_type": "power_anomaly_ai", "summary": "test"},
        "push": {"alarm_type": "power_anomaly_ai", "risk_level": "warning"},
    }


def _fake_response(status_code: int, body: dict | None = None):
    return type(
        "R",
        (),
        {"status_code": status_code, "json": lambda self=None: body or {}},
    )()


@pytest.mark.asyncio
async def test_forward_normal_ml_id_propagated(payloads):
    """정상 — ML forward 201 → ml_id 추출 → alarm forward 에 포함."""
    ml_resp = _fake_response(201, {"id": 42})
    alarm_resp = _fake_response(201, {"alarm_id": 7, "event_id": 3})

    with patch("services.anomaly_alarm.FORWARD_ENABLED", True), patch(
        "services.anomaly_alarm.post_to_drf",
        new=AsyncMock(side_effect=[ml_resp, alarm_resp]),
    ) as mock_post, patch(
        "services.anomaly_alarm.push_alarm", new=AsyncMock()
    ) as mock_push:
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=payloads["ml"],
            alarm_payload=payloads["alarm"],
            push_payload=payloads["push"],
            should_fire=True,
        )
        # background push task 실행 보장
        await asyncio.sleep(0)

    assert mock_post.call_count == 2
    # ML call
    ml_call_args = mock_post.call_args_list[0]
    assert ml_call_args.args[0] == anomaly_alarm.ML_PATH
    # alarm call — ml_anomaly_result_id=42 주입 확인
    alarm_call_args = mock_post.call_args_list[1]
    assert alarm_call_args.args[0] == anomaly_alarm.ALARM_PATH
    assert alarm_call_args.args[1]["ml_anomaly_result_id"] == 42
    mock_push.assert_awaited_once_with(payloads["push"])


@pytest.mark.asyncio
async def test_forward_ml_failure_passes_null_ml_id(payloads):
    """ML forward 실패 (None) → alarm forward 는 진행, ml_anomaly_result_id=None."""
    alarm_resp = _fake_response(201, {"alarm_id": 7, "event_id": 3})

    with patch("services.anomaly_alarm.FORWARD_ENABLED", True), patch(
        "services.anomaly_alarm.post_to_drf",
        new=AsyncMock(side_effect=[None, alarm_resp]),
    ) as mock_post, patch("services.anomaly_alarm.push_alarm", new=AsyncMock()):
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=payloads["ml"],
            alarm_payload=payloads["alarm"],
            push_payload=payloads["push"],
            should_fire=True,
        )

    assert mock_post.call_count == 2
    alarm_call_args = mock_post.call_args_list[1]
    assert alarm_call_args.args[1]["ml_anomaly_result_id"] is None


@pytest.mark.asyncio
async def test_forward_should_fire_false_skips_push_and_alarm(payloads):
    """should_fire=False — push/alarm skip, ML forward 만 (운영 추적)."""
    ml_resp = _fake_response(201, {"id": 42})

    with patch("services.anomaly_alarm.FORWARD_ENABLED", True), patch(
        "services.anomaly_alarm.post_to_drf", new=AsyncMock(return_value=ml_resp)
    ) as mock_post, patch(
        "services.anomaly_alarm.push_alarm", new=AsyncMock()
    ) as mock_push:
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=payloads["ml"],
            alarm_payload=payloads["alarm"],
            push_payload=payloads["push"],
            should_fire=False,
        )

    assert mock_post.call_count == 1
    assert mock_post.call_args.args[0] == anomaly_alarm.ML_PATH
    mock_push.assert_not_called()


@pytest.mark.asyncio
async def test_forward_kill_switch_off_returns_immediately(payloads):
    """FORWARD_ENABLED=False — 즉시 return, 모든 외부 호출 skip."""
    with patch("services.anomaly_alarm.FORWARD_ENABLED", False), patch(
        "services.anomaly_alarm.post_to_drf", new=AsyncMock()
    ) as mock_post, patch(
        "services.anomaly_alarm.push_alarm", new=AsyncMock()
    ) as mock_push:
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=payloads["ml"],
            alarm_payload=payloads["alarm"],
            push_payload=payloads["push"],
            should_fire=True,
        )

    mock_post.assert_not_called()
    mock_push.assert_not_called()


@pytest.mark.asyncio
async def test_forward_push_independent_of_ml_hang(payloads):
    """push 독립성 — ML forward 가 hang 해도 push 는 그 전에 호출됨 (C12 효과).

    실제 운영의 핵심 보장: DRF SQLite lock 등으로 ML POST 가 timeout 까지 hang
    해도 브라우저 알람 push 는 그 영향 받지 않음.
    """
    push_called = asyncio.Event()
    ml_resp = _fake_response(201, {"id": 42})
    alarm_resp = _fake_response(201, {"alarm_id": 7, "event_id": 3})

    async def hang_then_ok(*args, **kwargs):
        # ML 만 hang. alarm 은 정상 응답.
        if args[0] == anomaly_alarm.ML_PATH:
            await asyncio.sleep(0.3)
            return ml_resp
        return alarm_resp

    async def mark_push(payload):
        push_called.set()

    with patch("services.anomaly_alarm.FORWARD_ENABLED", True), patch(
        "services.anomaly_alarm.post_to_drf", new=AsyncMock(side_effect=hang_then_ok)
    ), patch("services.anomaly_alarm.push_alarm", new=mark_push):
        task = asyncio.create_task(
            anomaly_alarm.forward_inference_e2e(
                ml_payload=payloads["ml"],
                alarm_payload=payloads["alarm"],
                push_payload=payloads["push"],
                should_fire=True,
            )
        )
        # ML 이 hang 중 (0.3s) push 는 이미 호출됐어야 함
        await asyncio.wait_for(push_called.wait(), timeout=0.1)
        await task  # cleanup
