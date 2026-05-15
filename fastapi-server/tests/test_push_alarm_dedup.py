"""websocket.services.alarm_queue.push_alarm fingerprint dedup 단위 테스트 (Step 1).

[검증 대상]
- 같은 fingerprint 의 두 번째 push 는 LPUSH skip + counter +1 (Celery retry 케이스)
- fingerprint 다른 두 payload 는 둘 다 LPUSH (정상 알람 흐름)
- fingerprint 형식 모르는 payload (event_id/anomaly_meta 둘 다 없음) 는 dedup 미적용
- dedup_ttl 인자화 — 짧게 (0.1s) 주면 TTL 후 같은 fp 도 다시 LPUSH 가능
- _payload_fingerprint 룰/AI 분기 정확성

[Redis mock]
실제 Redis 안 띄움. `core.redis_client.get_redis` 를 patch 하고 AsyncMock 으로
set/lpush/ltrim 호출만 추적. SET NX EX 의 반환값은 `set.side_effect` 로 시나리오별
제어. counter 는 prometheus_client `_value.get()` 로 직접 검증.
"""

from unittest.mock import AsyncMock, patch

import pytest

from websocket.services import alarm_queue


def _make_redis_mock(set_returns: list[bool]) -> AsyncMock:
    """fake redis client — set 은 side_effect 리스트, lpush/ltrim 은 정상 응답.

    Args:
        set_returns: r.set NX EX 의 순차 반환값. True=첫 도착자, False=이미 set.
    """
    redis = AsyncMock()
    redis.set = AsyncMock(side_effect=set_returns)
    redis.lpush = AsyncMock(return_value=1)
    redis.ltrim = AsyncMock(return_value=True)
    return redis


@pytest.mark.asyncio
async def test_rule_alarm_duplicate_fingerprint_dedups():
    """룰 알람 — 같은 event_id+risk_level 의 두 번째 호출은 LPUSH 안 함."""
    redis = _make_redis_mock(set_returns=[True, False])
    payload = {
        "event_id": 42,
        "alarm_type": "gas_threshold",
        "risk_level": "danger",
        "summary": "test",
    }

    before = alarm_queue.push_alarm_dedup_hits._value.get()
    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.push_alarm(payload)
        await alarm_queue.push_alarm(payload)

    # 첫 도착자만 LPUSH, 두 번째는 dedup 으로 skip
    assert redis.lpush.await_count == 1
    assert redis.ltrim.await_count == 1
    assert redis.set.await_count == 2
    # counter +1
    assert alarm_queue.push_alarm_dedup_hits._value.get() - before == 1


@pytest.mark.asyncio
async def test_distinct_fingerprints_both_push():
    """fingerprint 다른 두 payload (다른 event_id) 는 둘 다 LPUSH."""
    redis = _make_redis_mock(set_returns=[True, True])
    payload_a = {"event_id": 42, "risk_level": "danger"}
    payload_b = {"event_id": 99, "risk_level": "danger"}

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.push_alarm(payload_a)
        await alarm_queue.push_alarm(payload_b)

    assert redis.lpush.await_count == 2


@pytest.mark.asyncio
async def test_ai_alarm_fingerprint_includes_device_channel():
    """AI 알람 — anomaly_meta 의 device_id/channel/risk_level 조합으로 fingerprint."""
    redis = _make_redis_mock(set_returns=[True, False])
    payload = {
        "alarm_type": "power_anomaly_ai",
        "risk_level": "warning",
        "anomaly_meta": {
            "combined_risk": "predict_warn",
            "anomaly_score": -0.08,
            "device_id": "device_63200c3afd12",
            "channel": 1,
            "data_type": "watt",
        },
    }

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.push_alarm(payload)
        await alarm_queue.push_alarm(payload)

    # 같은 (device, channel, risk_level) → 두 번째 dedup
    assert redis.lpush.await_count == 1
    # set 키에 device/channel 포함됐는지 확인
    set_call_key = redis.set.call_args_list[0].args[0]
    assert "device_63200c3afd12" in set_call_key
    assert ":1:" in set_call_key  # channel 1
    assert "warning" in set_call_key


@pytest.mark.asyncio
async def test_unrecognized_payload_skips_dedup():
    """fingerprint 형식 모르는 payload (event_id/anomaly_meta/source_label 모두 없음)
    는 dedup 미적용 — 매번 LPUSH (set 호출 자체 안 함).
    """
    redis = _make_redis_mock(set_returns=[True, True])
    # geofence_intrusion 은 event_id 없는 경로로 들어오는 케이스 가정.
    # gas_clear/power_clear 은 별도 source_label 기반 dedup 분기 (아래 테스트) 라
    # 본 케이스는 "어느 분기에도 안 맞는 payload" 로 따로 검증.
    payload = {
        "alarm_type": "geofence_intrusion",
        "risk_level": "warning",
        "summary": "fallback",
    }

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.push_alarm(payload)
        await alarm_queue.push_alarm(payload)

    assert redis.set.await_count == 0  # dedup 검사 자체 skip
    assert redis.lpush.await_count == 2  # 둘 다 LPUSH


@pytest.mark.asyncio
async def test_push_alarm_dedupes_gas_clear_by_source_label():
    """gas 9 종 (co/h2s/co2/...) 이 같은 source_label 로 9 push → 첫 도착만 LPUSH.

    실제 운영 시나리오: `fire_clear_notification_task` 가 가스 9 종 각각 호출되어
    같은 센서의 정상화 push 가 짧은 시간 안에 9 건 들어옴. source_label 단위
    fingerprint 로 dedup 해서 패널 9줄 도배 방지.
    """
    redis = _make_redis_mock(set_returns=[True, False])
    payload = {
        "alarm_type": "gas_clear",
        "risk_level": "normal",
        "source_label": "공장동-가스센서-01",
    }

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.push_alarm(payload)
        await alarm_queue.push_alarm(payload)

    assert redis.lpush.await_count == 1
    assert redis.set.await_count == 2
    # fingerprint 키에 source_label 과 alarm_type 포함
    set_call_key = redis.set.call_args_list[0].args[0]
    assert "clear:gas_clear:공장동-가스센서-01" in set_call_key


@pytest.mark.asyncio
async def test_push_alarm_does_not_dedupe_gas_clear_across_sources():
    """다른 source_label 의 정상화는 별개 알람 → 둘 다 LPUSH."""
    redis = _make_redis_mock(set_returns=[True, True])
    payload_a = {
        "alarm_type": "gas_clear",
        "risk_level": "normal",
        "source_label": "공장동-가스센서-01",
    }
    payload_b = {
        "alarm_type": "gas_clear",
        "risk_level": "normal",
        "source_label": "사무동-가스센서-02",
    }

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.push_alarm(payload_a)
        await alarm_queue.push_alarm(payload_b)

    assert redis.lpush.await_count == 2


@pytest.mark.asyncio
async def test_ai_alarm_without_meta_skips_dedup():
    """AI alarm_type 인데 anomaly_meta 누락 — fingerprint 불가, dedup skip."""
    redis = _make_redis_mock(set_returns=[True, True])
    payload = {"alarm_type": "power_anomaly_ai", "risk_level": "warning"}

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.push_alarm(payload)
        await alarm_queue.push_alarm(payload)

    assert redis.set.await_count == 0
    assert redis.lpush.await_count == 2


@pytest.mark.asyncio
async def test_dedup_ttl_arg_passed_to_set():
    """dedup_ttl 인자가 r.set 의 ex 파라미터로 그대로 전달되는지."""
    redis = _make_redis_mock(set_returns=[True])
    payload = {"event_id": 7, "risk_level": "warning"}

    with patch("websocket.services.alarm_queue.get_redis", return_value=redis):
        await alarm_queue.push_alarm(payload, dedup_ttl=5)

    set_kwargs = redis.set.call_args.kwargs
    assert set_kwargs.get("ex") == 5
    assert set_kwargs.get("nx") is True


def test_payload_fingerprint_rule_alarm():
    """룰 알람 fingerprint — event:{id}:{risk_level}."""
    fp = alarm_queue._payload_fingerprint(
        {"event_id": 42, "risk_level": "danger", "alarm_type": "gas_threshold"}
    )
    assert fp == "event:42:danger"


def test_payload_fingerprint_ai_alarm():
    """AI 알람 fingerprint — ai:{alarm_type}:{device}:{channel}:{risk_level}."""
    fp = alarm_queue._payload_fingerprint(
        {
            "alarm_type": "power_anomaly_ai",
            "risk_level": "warning",
            "anomaly_meta": {"device_id": "dev_1", "channel": 3},
        }
    )
    assert fp == "ai:power_anomaly_ai:dev_1:3:warning"


def test_payload_fingerprint_unknown_returns_none():
    """fingerprint 형식 모름 — None (dedup skip)."""
    # source_label 없는 정상화 — 분기 매칭은 되지만 키 생성 불가 → None
    assert alarm_queue._payload_fingerprint({"alarm_type": "gas_clear"}) is None
    assert alarm_queue._payload_fingerprint({}) is None
    # AI alarm_type 인데 meta 미포함 — None
    assert alarm_queue._payload_fingerprint({"alarm_type": "power_anomaly_ai"}) is None


def test_payload_fingerprint_clear_alarm():
    """정상화 알람 fingerprint — clear:{alarm_type}:{source_label}."""
    fp = alarm_queue._payload_fingerprint(
        {
            "alarm_type": "gas_clear",
            "risk_level": "normal",
            "source_label": "공장동-가스센서-01",
        }
    )
    assert fp == "clear:gas_clear:공장동-가스센서-01"

    fp_power = alarm_queue._payload_fingerprint(
        {
            "alarm_type": "power_clear",
            "risk_level": "normal",
            "source_label": "송풍기-A",
        }
    )
    assert fp_power == "clear:power_clear:송풍기-A"
