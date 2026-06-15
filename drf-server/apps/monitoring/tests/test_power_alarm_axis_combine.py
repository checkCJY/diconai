"""
전력 알람 라우터 W·A·V 축 통합 회귀 테스트 (Phase 1+2).

[회귀 커버 대상]
- trigger_power_alarms()가 data_type별로 해당 축만 평가하고 다른 두 축은 Redis 캐시에서 읽음
- max-of-3 aggregate로 try_transition 호출 (Phase 1 계약 — state_key 변경 금지)
- 한 채널에서 W WARNING → A DANGER 진입 시 fire_power_danger 1회만 발화 (중복 차단)
- 세 축 NORMAL 회복 시 fire_power_clear 발화 + state 정리
- 채널 라벨은 PowerDevice.channel_meta["{ch}"]["name"]에서 조회

[설계 결정]
fire_power_*_task를 mock하여 발화 횟수와 인자를 검증. 실제 Celery 실행은 분리.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.core.constants import RiskLevel
from apps.monitoring.models import PowerData
from apps.monitoring.services.power_alarm import (
    _axis_risk_key,
    _state_key,
    trigger_power_alarms,
)


@pytest.fixture(autouse=True)
def clear_cache(settings):
    # 이 파일은 축 결합/라벨/복구 로직을 단일 틱으로 검증한다 — 2틱 confirm(#110)과
    # 무관하므로 즉시 발화(1틱)로 고정해 DANGER fire 를 단언한다. confirm 게이트 자체는
    # test_danger_confirm.py 가 별도 커버.
    settings.DANGER_CONFIRM_TICKS = 1
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def device_with_meta(power_device):
    """channel 1에 W=1000/A=10/V=380 정격 + 라벨 '테스트 모터' 시드."""
    power_device.channel_meta = {
        "1": {"name": "테스트 모터", "rated_w": 1000, "rated_a": 10, "rated_v": 380}
    }
    power_device.save()
    return power_device


_tick_counter = {"n": 0}


def _make_objs(device, data_type: str, channel: int, value: float):
    """PowerData row 1건을 DB에 저장하고 list로 반환. measured_at은 매 호출마다 1초씩 진행."""
    _tick_counter["n"] += 1
    measured_at = datetime.now(timezone.utc) + timedelta(seconds=_tick_counter["n"])
    obj = PowerData.objects.create(
        power_device=device,
        channel=channel,
        data_type=data_type,
        value=value,
        measured_at=measured_at,
    )
    return [obj]


def _warn_mock_with_id():
    """fire_power_warning_task.apply_async가 pickle 가능한 id를 반환하도록 mock 세팅."""
    from unittest.mock import MagicMock

    m = MagicMock()
    m.apply_async.return_value = MagicMock(id="task-warn-fake-id")
    return m


# ── 단축 W·A·V 시나리오 ──────────────────────────────────────────────


@pytest.mark.django_db
def test_axis_caches_independently_per_channel(device_with_meta):
    """축별 캐시 키가 (device, channel, axis) 3-tuple로 격리."""
    trigger_power_alarms(_make_objs(device_with_meta, "watt", 1, 850), device_with_meta)
    trigger_power_alarms(
        _make_objs(device_with_meta, "current", 1, 9.0), device_with_meta
    )
    trigger_power_alarms(
        _make_objs(device_with_meta, "voltage", 1, 380), device_with_meta
    )

    dev_id = device_with_meta.id
    assert cache.get(_axis_risk_key(dev_id, 1, "watt")) == RiskLevel.WARNING
    assert cache.get(_axis_risk_key(dev_id, 1, "current")) == RiskLevel.WARNING
    assert cache.get(_axis_risk_key(dev_id, 1, "voltage")) == RiskLevel.NORMAL


@pytest.mark.django_db
def test_w_warning_then_a_danger_fires_once_each(device_with_meta):
    """W WARNING(82%) → A DANGER(106%) → 후속 watt 틱이 aggregate DANGER 발화.

    [#110 계약] non-watt 축(전류/전압) DANGER 는 자기 틱에 즉시 발화하지 않는다 —
    전류/전압 도착 시점의 watt 캐시가 stale 일 수 있어 조기 발화를 막는다. 대신 다음
    watt 틱이 3축 max(aggregate)로 DANGER 를 실어 발화한다(power_alarm.py L260-264).
    """
    with (
        patch(
            "apps.monitoring.services.power_alarm.fire_power_warning_task",
            new=_warn_mock_with_id(),
        ) as fire_warn,
        patch(
            "apps.monitoring.services.power_alarm.fire_power_danger_task"
        ) as fire_danger,
    ):
        # 1) W 820W (82% of 1000) → aggregate WARNING → 경고 타이머 1회
        trigger_power_alarms(
            _make_objs(device_with_meta, "watt", 1, 820), device_with_meta
        )
        assert fire_warn.apply_async.call_count == 1
        assert fire_danger.delay.call_count == 0

        # 2) A 10.6A (106% of 10) → 전류 축 DANGER 캐시. 자기 틱은 발화 보류(watt 아님)
        trigger_power_alarms(
            _make_objs(device_with_meta, "current", 1, 10.6), device_with_meta
        )
        assert fire_danger.delay.call_count == 0  # 아직 보류

        # 3) W 820W 재도착 → aggregate=max(watt WARNING, current DANGER)=DANGER → 1회 발화
        trigger_power_alarms(
            _make_objs(device_with_meta, "watt", 1, 820), device_with_meta
        )
        assert fire_danger.delay.call_count == 1

        # 4) V 350V (92% of 380, 저전압 WARNING) → aggregate 여전히 DANGER, 추가 fire 없음
        trigger_power_alarms(
            _make_objs(device_with_meta, "voltage", 1, 350), device_with_meta
        )
        assert fire_danger.delay.call_count == 1  # 중복 차단


@pytest.mark.django_db
def test_voltage_low_danger_fires_on_next_watt_tick(device_with_meta):
    """저전압 단독(342V = 90% of 380) DANGER → 다음 watt 틱이 aggregate 로 발화.

    [#110 계약] 전압 축 DANGER 는 자기 틱에 즉시 발화하지 않고(watt 캐시 stale 방지)
    후속 watt 틱이 3축 max 로 실어 발화한다. '저전압 단독 위험' 은 여전히 탐지되되
    watt 송신 주기만큼 지연된다 — 전력 장비는 매 사이클 3축을 모두 보내므로 실효 지연 작음.
    """
    with patch(
        "apps.monitoring.services.power_alarm.fire_power_danger_task"
    ) as fire_danger:
        # 1) V 342V (90%) → 전압 축 DANGER 캐시, 자기 틱은 보류
        trigger_power_alarms(
            _make_objs(device_with_meta, "voltage", 1, 342), device_with_meta
        )
        assert fire_danger.delay.call_count == 0

        # 2) W 500W (50% NORMAL) 도착 → aggregate=max(watt NORMAL, voltage DANGER)=DANGER
        trigger_power_alarms(
            _make_objs(device_with_meta, "watt", 1, 500), device_with_meta
        )
        assert fire_danger.delay.call_count == 1
        # 채널 라벨 검증 — channel_meta["1"]["name"] = "테스트 모터"
        _, _, _, _, label = fire_danger.delay.call_args[0]
        assert label == "테스트 모터"


@pytest.mark.django_db
def test_recovery_clears_state(device_with_meta):
    """W DANGER → 정상값 복귀 → fire_power_clear 발화 + state 정리."""
    with (
        patch(
            "apps.monitoring.services.power_alarm.fire_power_danger_task"
        ) as fire_danger,
        patch(
            "apps.monitoring.services.power_alarm.fire_power_clear_task"
        ) as fire_clear,
    ):
        # DANGER 진입
        trigger_power_alarms(
            _make_objs(device_with_meta, "watt", 1, 1200), device_with_meta
        )
        assert fire_danger.delay.call_count == 1
        # 정상 복귀 — 세 축 모두 NORMAL 캐시
        trigger_power_alarms(
            _make_objs(device_with_meta, "watt", 1, 500), device_with_meta
        )
        assert fire_clear.delay.call_count == 1
        # state_key 정리됨
        assert cache.get(_state_key(device_with_meta.id, 1)) is None


@pytest.mark.django_db
def test_unknown_data_type_ignored(device_with_meta):
    """알람 대상 아닌 data_type은 early return."""
    from types import SimpleNamespace

    fake_obj = SimpleNamespace(data_type="onoff", channel=1, value=820)
    with patch(
        "apps.monitoring.services.power_alarm.fire_power_warning_task"
    ) as fire_warn:
        trigger_power_alarms([fake_obj], device_with_meta)
        assert fire_warn.apply_async.call_count == 0


@pytest.mark.django_db
def test_unlabeled_channel_falls_back_to_chn_format(power_device):
    """channel_meta에 키 없는 채널 → "CH{n}" 라벨."""
    with patch(
        "apps.monitoring.services.power_alarm.fire_power_danger_task"
    ) as fire_danger:
        trigger_power_alarms(_make_objs(power_device, "watt", 5, 3000), power_device)
        assert fire_danger.delay.call_count == 1
        _, _, _, _, label = fire_danger.delay.call_args[0]
        assert label == "CH5"
