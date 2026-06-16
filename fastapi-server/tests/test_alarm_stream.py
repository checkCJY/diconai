"""alarm_queue Stream 전환 단위 테스트 — XADD push / XREAD 배치 read / 커서 / 타입가드.

[검증 대상]
- push_alarm 이 LPUSH/LTRIM 대신 XADD(MAXLEN ~ 10000) 1회 호출 (트리밍 포함)
- read_alarms_blocking 이 XREAD 배치(N건)를 순서대로 반환 + 커서를 배치 마지막 ID로 전진
- 빈 결과/예외 시 커서 동결 ((last_id, []) 반환)
- 배치 중 일부 디코드 실패 시 나머지 보존, 커서는 마지막 ID로 전진
- queue_len 이 XLEN 사용
- reset_stream_if_wrongtype 이 TYPE=list 일 때만 DEL (stream/none 보존)
- stream_tail_id / _id_ms (stream lag 계산용)

[Redis mock]
test_push_alarm_dedup.py 와 동일 — 실제 Redis 안 띄우고 get_redis 를 AsyncMock 으로
patch. fakeredis 미사용 (기존 알람 테스트 패턴 일치, 의존성 추가 없음).
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from websocket.services import alarm_queue
from websocket.services.alarm_queue import ALARM_QUEUE_KEY, MAX_QUEUE_LEN


@pytest.mark.asyncio
async def test_push_alarm_uses_xadd_with_maxlen():
    """push 는 XADD(MAXLEN ~ 10000) 1회 — LPUSH/LTRIM 미사용, payload 는 data 필드."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.xadd = AsyncMock(return_value="1-0")
    redis.xlen = AsyncMock(return_value=1)
    payload = {"event_id": 1, "risk_level": "danger", "summary": "x"}

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.push_alarm(payload)

    assert redis.xadd.await_count == 1
    args, kwargs = redis.xadd.call_args
    assert args[0] == ALARM_QUEUE_KEY
    # 단일 필드 "data" 에 JSON 직렬화해 적재 (read 시 json.loads 로 복원)
    assert json.loads(args[1]["data"])["event_id"] == 1
    # 트리밍은 MAXLEN ~ 로 XADD 에 포함 — 별도 LTRIM 명령 없음
    assert kwargs["maxlen"] == MAX_QUEUE_LEN
    assert kwargs["approximate"] is True
    assert not redis.lpush.called
    assert not redis.ltrim.called


@pytest.mark.asyncio
async def test_read_alarms_blocking_returns_batch_in_order():
    """XREAD 가 N건 배치를 주면 순서 보존 + 커서를 배치 마지막 entry ID 로 전진."""
    redis = AsyncMock()
    entries = [
        ("1-0", {"data": json.dumps({"n": 1})}),
        ("2-0", {"data": json.dumps({"n": 2})}),
        ("3-0", {"data": json.dumps({"n": 3})}),
    ]
    redis.xread = AsyncMock(return_value=[(ALARM_QUEUE_KEY, entries)])
    redis.xlen = AsyncMock(return_value=3)

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        new_last_id, payloads = await alarm_queue.read_alarms_blocking("$", timeout=1)

    assert new_last_id == "3-0"  # 배치 마지막 ID
    assert [p["n"] for p in payloads] == [1, 2, 3]  # FIFO 순서 보존
    # XREAD 가 커서 last_id 로 호출 + timeout(초) → BLOCK ms 변환
    call = redis.xread.call_args
    assert call.args[0] == {ALARM_QUEUE_KEY: "$"}
    assert call.kwargs["block"] == 1000


@pytest.mark.asyncio
async def test_read_alarms_blocking_empty_freezes_cursor():
    """BLOCK timeout (None 반환) — 커서 유지, 빈 리스트 반환."""
    redis = AsyncMock()
    redis.xread = AsyncMock(return_value=None)  # redis-py 는 timeout 시 None
    redis.xlen = AsyncMock(return_value=0)

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        new_last_id, payloads = await alarm_queue.read_alarms_blocking("5-0", timeout=1)

    assert new_last_id == "5-0"  # 커서 동결
    assert payloads == []
    # 빈 결과면 길이 갱신 안 함 (소비분 없음)
    assert not redis.xlen.called


@pytest.mark.asyncio
async def test_read_alarms_blocking_exception_freezes_cursor():
    """XREAD 예외 (Redis 일시 장애) — 커서 동결 + 빈 리스트 (slow-retry)."""
    redis = AsyncMock()
    redis.xread = AsyncMock(side_effect=ConnectionError("boom"))

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        new_last_id, payloads = await alarm_queue.read_alarms_blocking("7-0", timeout=1)

    assert new_last_id == "7-0"
    assert payloads == []


@pytest.mark.asyncio
async def test_read_alarms_blocking_skips_bad_entry_but_advances_cursor():
    """배치 중 디코드 실패 entry 는 건너뛰고 나머지 보존, 커서는 배치 마지막 ID."""
    redis = AsyncMock()
    entries = [
        ("1-0", {"data": json.dumps({"n": 1})}),
        ("2-0", {"data": "{not valid json"}),  # 깨진 entry
        ("3-0", {"data": json.dumps({"n": 3})}),
    ]
    redis.xread = AsyncMock(return_value=[(ALARM_QUEUE_KEY, entries)])
    redis.xlen = AsyncMock(return_value=3)

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        new_last_id, payloads = await alarm_queue.read_alarms_blocking("$", timeout=1)

    assert [p["n"] for p in payloads] == [1, 3]  # 깨진 2-0 만 drop
    assert new_last_id == "3-0"  # 커서는 끝까지 전진 (재읽기 방지)


@pytest.mark.asyncio
async def test_queue_len_uses_xlen():
    """queue_len 은 LLEN 이 아니라 XLEN."""
    redis = AsyncMock()
    redis.xlen = AsyncMock(return_value=7)

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        assert await alarm_queue.queue_len() == 7

    assert redis.xlen.await_count == 1
    assert not redis.llen.called


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key_type,should_delete",
    [("list", True), ("stream", False), ("none", False)],
)
async def test_reset_stream_deletes_only_legacy_list(key_type, should_delete):
    """TYPE=list 일 때만 DEL — stream/none 은 보존 (재시작마다 wipe 방지)."""
    redis = AsyncMock()
    redis.type = AsyncMock(return_value=key_type)

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.reset_stream_if_wrongtype()

    assert redis.delete.called is should_delete


@pytest.mark.asyncio
async def test_reset_stream_swallows_exception():
    """TYPE 조회 예외는 삼켜 startup 을 막지 않는다."""
    redis = AsyncMock()
    redis.type = AsyncMock(side_effect=ConnectionError("boom"))

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.reset_stream_if_wrongtype()  # 예외 전파 안 함


@pytest.mark.asyncio
async def test_stream_tail_id_returns_last_entry_id():
    """stream_tail_id 는 XREVRANGE COUNT 1 의 entry ID 반환, 비면 None."""
    redis = AsyncMock()
    redis.xrevrange = AsyncMock(return_value=[("9-0", {"data": "x"})])
    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        assert await alarm_queue.stream_tail_id() == "9-0"

    redis.xrevrange = AsyncMock(return_value=[])  # 빈 스트림
    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        assert await alarm_queue.stream_tail_id() is None


def test_id_ms_parses_millisecond_part():
    """entry ID '<ms>-<seq>' 에서 ms 정수만 파싱 (lag 시간차 계산용)."""
    assert alarm_queue._id_ms("1718000000123-0") == 1718000000123
    assert alarm_queue._id_ms("5-3") == 5
