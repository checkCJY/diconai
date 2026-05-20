"""fastapi AI mute 마킹 + state machine 검증.

[검증 대상]
- ai_mute.mark_ai_recent — device_id/channel None 이면 skip, Redis 장애 silent
- ai_mute.mark_ai_state / get_ai_state — T4 5-state round-trip + fail-safe
- anomaly_alarm.forward_inference_e2e — T4 D2 후 ML/AlarmRecord forward 만 (push
  / mark_ai_recent 책임은 호출자로 이전)

[redis mock 패턴]
core.redis_client.get_redis 를 patch + AsyncMock 으로 r.set/r.get 호출 추적.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services import ai_mute


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


# ── T4 — AI inference 5-state machine ───────────────────────────────────────
# mark_ai_state / get_ai_state 의 round-trip · TTL 만료 · 잘못된 입력 분기 검증.
# 기존 mark_ai_recent 테스트와 같은 redis_mock 패턴 차용 (get_redis patch).


@pytest.mark.asyncio
async def test_mark_ai_state_sets_single_key_with_value():
    """mark_ai_state — 단일 키에 state.value SET (격상 bypass 다중 키와 다름)."""
    redis_mock = AsyncMock()
    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        await ai_mute.mark_ai_state(
            device_id="dev_42",
            channel=1,
            data_type="watt",
            state=ai_mute.AIInferenceState.INFERRED_NORMAL,
        )

    redis_mock.set.assert_awaited_once_with(
        "ai_state:dev_42:1:watt", "inferred_normal", ex=60
    )


@pytest.mark.asyncio
async def test_mark_ai_state_skips_when_any_dimension_none():
    """device_id / channel / data_type 어느 하나라도 None 이면 SET 호출 skip."""
    redis_mock = AsyncMock()
    state = ai_mute.AIInferenceState.WARMING_UP

    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        await ai_mute.mark_ai_state(None, 1, "watt", state)
        await ai_mute.mark_ai_state("dev_1", None, "watt", state)
        await ai_mute.mark_ai_state("dev_1", 1, None, state)

    redis_mock.set.assert_not_called()


@pytest.mark.asyncio
async def test_mark_ai_state_rejects_non_enum():
    """state 인자가 AIInferenceState 멤버 아닐 시 silent skip (str 직접 전달 방지)."""
    redis_mock = AsyncMock()
    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        # 일부러 잘못된 타입 — 타입 힌트 위반이지만 런타임 방어 검증
        await ai_mute.mark_ai_state("dev_1", 1, "watt", "fired")  # type: ignore[arg-type]

    redis_mock.set.assert_not_called()


@pytest.mark.asyncio
async def test_mark_ai_state_silent_fail_on_redis_error():
    """Redis 장애 시 예외 swallow — fail-safe (호출자 push 흐름 비차단)."""
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(side_effect=ConnectionError("redis down"))

    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        await ai_mute.mark_ai_state("dev_1", 1, "watt", ai_mute.AIInferenceState.FIRED)


@pytest.mark.asyncio
async def test_get_ai_state_returns_enum_when_set():
    """get_ai_state — Redis 에 마킹된 value 를 AIInferenceState 로 복원."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=b"inferred_failed")

    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        result = await ai_mute.get_ai_state("dev_42", 1, "watt")

    assert result == ai_mute.AIInferenceState.INFERRED_FAILED
    redis_mock.get.assert_awaited_once_with("ai_state:dev_42:1:watt")


@pytest.mark.asyncio
async def test_get_ai_state_handles_str_value():
    """redis-py 가 str 반환하는 경우 (decode_responses=True) 도 정상 복원."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value="warming_up")

    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        result = await ai_mute.get_ai_state("dev_1", 1, "watt")

    assert result == ai_mute.AIInferenceState.WARMING_UP


@pytest.mark.asyncio
async def test_get_ai_state_returns_none_when_missing():
    """키 미설정/만료 — get_ai_state None 반환."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)

    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        result = await ai_mute.get_ai_state("dev_1", 1, "watt")

    assert result is None


@pytest.mark.asyncio
async def test_get_ai_state_returns_none_when_dimension_none():
    """입력 차원 중 하나라도 None 이면 redis 조회 없이 None 반환."""
    redis_mock = AsyncMock()
    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        assert await ai_mute.get_ai_state(None, 1, "watt") is None
        assert await ai_mute.get_ai_state("dev_1", None, "watt") is None
        assert await ai_mute.get_ai_state("dev_1", 1, None) is None

    redis_mock.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_ai_state_returns_none_on_unknown_value():
    """저장된 값이 Enum 멤버 아닐 시 (옛 형식·손상) None + WARN 로깅."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=b"corrupted_state")

    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        result = await ai_mute.get_ai_state("dev_1", 1, "watt")

    assert result is None


@pytest.mark.asyncio
async def test_get_ai_state_fail_open_on_redis_error():
    """Redis 장애 시 None 반환 (fail-open) — decide_alarm 이 fail-safe 분기."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=ConnectionError("redis down"))

    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        result = await ai_mute.get_ai_state("dev_1", 1, "watt")

    assert result is None


@pytest.mark.asyncio
async def test_mark_then_get_round_trip_all_states():
    """5 state 전부 round-trip — mark 한 value 가 get 시 같은 Enum 으로 복원."""
    storage: dict[str, str] = {}

    async def fake_set(key, value, ex=None):
        storage[key] = value

    async def fake_get(key):
        v = storage.get(key)
        return v.encode() if v is not None else None

    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(side_effect=fake_set)
    redis_mock.get = AsyncMock(side_effect=fake_get)

    with patch("services.ai_mute.get_redis", return_value=redis_mock):
        for state in ai_mute.AIInferenceState:
            await ai_mute.mark_ai_state("dev_1", 1, "watt", state)
            got = await ai_mute.get_ai_state("dev_1", 1, "watt")
            assert got == state, f"round-trip failed for {state}"
