"""services.anomaly_alarm.forward_inference_e2e 단위 테스트.

[T4 D2 변경]
push_payload 인자 + push_alarm 호출 + mark_ai_recent 호출 모두 제거.
호출자 (power_service.process_anomaly_inference) 가 decide_alarm 결정 후 직접 호출.
본 함수는 DRF 영속화만 — ML forward (매번) + AlarmRecord forward (alarm_payload 있을 때).

[검증 대상]
- 정상 — ML forward 201 → ml_id 캡처 → alarm forward (ml_id 포함)
- ML forward 실패 (response None) — ml_id=None, alarm forward 진행
- alarm_payload=None — ML forward 만
- kill switch off (FORWARD_ANOMALY_TO_DRF=false) — 즉시 return, post_to_drf 0회
"""

from unittest.mock import AsyncMock, patch

import pytest

from services import anomaly_alarm


@pytest.fixture
def payloads():
    return {
        "ml": {"sensor_type": "power", "anomaly_score": -0.07},
        "alarm": {"alarm_type": "power_anomaly_ai", "summary": "test"},
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

    with (
        patch("services.anomaly_alarm.FORWARD_ENABLED", True),
        patch(
            "services.anomaly_alarm.post_to_drf",
            new=AsyncMock(side_effect=[ml_resp, alarm_resp]),
        ) as mock_post,
    ):
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=payloads["ml"],
            alarm_payload=payloads["alarm"],
        )

    assert mock_post.call_count == 2
    ml_call_args = mock_post.call_args_list[0]
    assert ml_call_args.args[0] == anomaly_alarm.ML_PATH
    # alarm call — ml_anomaly_result_id=42 주입 확인
    alarm_call_args = mock_post.call_args_list[1]
    assert alarm_call_args.args[0] == anomaly_alarm.ALARM_PATH
    assert alarm_call_args.args[1]["ml_anomaly_result_id"] == 42


@pytest.mark.asyncio
async def test_forward_ml_failure_passes_null_ml_id(payloads):
    """ML forward 실패 (None) → alarm forward 는 진행, ml_anomaly_result_id=None."""
    alarm_resp = _fake_response(201, {"alarm_id": 7, "event_id": 3})

    with (
        patch("services.anomaly_alarm.FORWARD_ENABLED", True),
        patch(
            "services.anomaly_alarm.post_to_drf",
            new=AsyncMock(side_effect=[None, alarm_resp]),
        ) as mock_post,
    ):
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=payloads["ml"],
            alarm_payload=payloads["alarm"],
        )

    assert mock_post.call_count == 2
    alarm_call_args = mock_post.call_args_list[1]
    assert alarm_call_args.args[1]["ml_anomaly_result_id"] is None


@pytest.mark.asyncio
async def test_forward_alarm_payload_none_skips_alarm_forward(payloads):
    """alarm_payload=None — ML forward 만 (운영 추적), AlarmRecord forward skip."""
    ml_resp = _fake_response(201, {"id": 42})

    with (
        patch("services.anomaly_alarm.FORWARD_ENABLED", True),
        patch(
            "services.anomaly_alarm.post_to_drf", new=AsyncMock(return_value=ml_resp)
        ) as mock_post,
    ):
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=payloads["ml"],
            alarm_payload=None,
        )

    assert mock_post.call_count == 1
    assert mock_post.call_args.args[0] == anomaly_alarm.ML_PATH


@pytest.mark.asyncio
async def test_forward_kill_switch_off_returns_immediately(payloads):
    """FORWARD_ENABLED=False — 즉시 return, 모든 외부 호출 skip."""
    with (
        patch("services.anomaly_alarm.FORWARD_ENABLED", False),
        patch("services.anomaly_alarm.post_to_drf", new=AsyncMock()) as mock_post,
    ):
        await anomaly_alarm.forward_inference_e2e(
            ml_payload=payloads["ml"],
            alarm_payload=payloads["alarm"],
        )

    mock_post.assert_not_called()
