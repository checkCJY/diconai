"""fastapi AI 발화 시 mute 마킹 호출 검증 (Step 3).

[검증 대상]
- forward_inference_e2e — should_fire=True 시 mark_ai_recent 호출 (combined_risk
  → AI_TO_RULE_LEVEL 환산값 전달)
- should_fire=False — mark_ai_recent 호출 안 함
- combined_risk='predict_warn' → rule_level='warning' 환산 확인
- ai_mute.mark_ai_recent — device_id/channel None 이면 skip, Redis 장애 시 silent

[redis mock 패턴]
core.redis_client.get_redis 를 patch + AsyncMock 으로 r.set 호출 추적. anomaly_alarm
테스트는 mark_ai_recent 자체를 patch 해서 호출 인자 검증.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from services import ai_mute, anomaly_alarm


@pytest.fixture
def base_payloads():
    return {
        "ml": {"sensor_type": "power", "anomaly_score": -0.08},
        "alarm": {"alarm_type": "power_anomaly_ai", "summary": "test"},
        "push": {
            "alarm_type": "power_anomaly_ai",
            "risk_level": "warning",
            "anomaly_meta": {
                "combined_risk": "predict_warn",
                "anomaly_score": -0.08,
                "device_id": "dev_42",
                "channel": 1,
                "data_type": "watt",
            },
        },
    }


@pytest.mark.asyncio
async def test_forward_marks_ai_recent_on_fire(base_payloads):
    """should_fire=True 시 mark_ai_recent 가 fire-and-forget 호출됨.

    combined_risk='predict_warn' → AI_TO_RULE_LEVEL 환산으로 'warning' 전달.
    """
    ml_resp = type("R", (), {"status_code": 201, "json": lambda self=None: {"id": 1}})()
    alarm_resp = type("R", (), {"status_code": 201, "json": lambda self=None: {}})()

    with patch("services.anomaly_alarm.FORWARD_ENABLED", True), patch(
        "services.anomaly_alarm.post_to_drf",
        new=AsyncMock(side_effect=[ml_resp, alarm_resp]),
    ), patch("services.anomaly_alarm.push_alarm", new=AsyncMock()), patch(
        "services.anomaly_alarm.mark_ai_recent", new=AsyncMock()
    ) as mock_mark:
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=base_payloads["ml"],
            alarm_payload=base_payloads["alarm"],
            push_payload=base_payloads["push"],
            should_fire=True,
        )
        # mark_ai_recent 는 create_task 로 fire-and-forget — 한 turn 양보
        await asyncio.sleep(0)

    mock_mark.assert_awaited_once_with("dev_42", 1, "warning")


@pytest.mark.asyncio
async def test_forward_skips_mark_when_should_not_fire(base_payloads):
    """should_fire=False — mark_ai_recent / push 모두 skip, ML forward 만."""
    ml_resp = type("R", (), {"status_code": 201, "json": lambda self=None: {"id": 1}})()

    with patch("services.anomaly_alarm.FORWARD_ENABLED", True), patch(
        "services.anomaly_alarm.post_to_drf", new=AsyncMock(return_value=ml_resp)
    ), patch("services.anomaly_alarm.push_alarm", new=AsyncMock()), patch(
        "services.anomaly_alarm.mark_ai_recent", new=AsyncMock()
    ) as mock_mark:
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=base_payloads["ml"],
            alarm_payload=base_payloads["alarm"],
            push_payload=base_payloads["push"],
            should_fire=False,
        )
        await asyncio.sleep(0)

    mock_mark.assert_not_called()


@pytest.mark.asyncio
async def test_forward_marks_danger_when_combined_risk_danger(base_payloads):
    """combined_risk='danger' → rule_level='danger' 그대로 전달."""
    base_payloads["push"]["anomaly_meta"]["combined_risk"] = "danger"
    base_payloads["push"]["risk_level"] = "danger"

    ml_resp = type("R", (), {"status_code": 201, "json": lambda self=None: {"id": 1}})()
    alarm_resp = type("R", (), {"status_code": 201, "json": lambda self=None: {}})()

    with patch("services.anomaly_alarm.FORWARD_ENABLED", True), patch(
        "services.anomaly_alarm.post_to_drf",
        new=AsyncMock(side_effect=[ml_resp, alarm_resp]),
    ), patch("services.anomaly_alarm.push_alarm", new=AsyncMock()), patch(
        "services.anomaly_alarm.mark_ai_recent", new=AsyncMock()
    ) as mock_mark:
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=base_payloads["ml"],
            alarm_payload=base_payloads["alarm"],
            push_payload=base_payloads["push"],
            should_fire=True,
        )
        await asyncio.sleep(0)

    mock_mark.assert_awaited_once_with("dev_42", 1, "danger")


@pytest.mark.asyncio
async def test_ai_mute_skips_when_device_id_none():
    """mark_ai_recent — device_id None 이면 set 호출 자체 skip."""
    redis_mock = AsyncMock()
    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        await ai_mute.mark_ai_recent(device_id=None, channel=1, rule_level="warning")
    redis_mock.set.assert_not_called()


@pytest.mark.asyncio
async def test_ai_mute_skips_when_channel_none():
    """mark_ai_recent — channel None 이면 set 호출 skip."""
    redis_mock = AsyncMock()
    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        await ai_mute.mark_ai_recent(
            device_id="dev_1", channel=None, rule_level="warning"
        )
    redis_mock.set.assert_not_called()


@pytest.mark.asyncio
async def test_ai_mute_sets_below_or_equal_levels():
    """mark_ai_recent rule_level=warning → normal/warning 2개 키 set (격상 bypass 보장)."""
    redis_mock = AsyncMock()
    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        await ai_mute.mark_ai_recent(
            device_id="dev_42", channel=1, rule_level="warning"
        )

    # normal + warning 두 키 set, danger 키는 set 안 됨
    assert redis_mock.set.await_count == 2
    set_keys = [call.args[0] for call in redis_mock.set.call_args_list]
    assert "ai_fired:dev_42:1:normal" in set_keys
    assert "ai_fired:dev_42:1:warning" in set_keys
    assert "ai_fired:dev_42:1:danger" not in set_keys


@pytest.mark.asyncio
async def test_ai_mute_silent_fail_on_redis_error():
    """Redis 장애 시 예외 swallow — 알람 push 흐름 비차단."""
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(side_effect=ConnectionError("redis down"))

    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        # 예외 raise 안 해야 함
        await ai_mute.mark_ai_recent(device_id="dev_1", channel=1, rule_level="warning")


@pytest.mark.asyncio
async def test_ai_mute_unknown_rule_level_skips():
    """알 수 없는 rule_level (e.g. 'critical') 은 마킹 skip — _LEVELS_AT_OR_BELOW 키 부재."""
    redis_mock = AsyncMock()
    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        await ai_mute.mark_ai_recent(
            device_id="dev_1", channel=1, rule_level="critical"
        )
    redis_mock.set.assert_not_called()
