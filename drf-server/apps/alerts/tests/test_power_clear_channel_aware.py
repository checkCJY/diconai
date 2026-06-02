"""전력 정상화(clear) 시 디바이스 Event 를 '마지막 활성 채널'에서만 RESOLVE.

[배경]
Event 병합은 (facility, event_type, power_device) 단위 — 채널 무시. 그래서 한
PowerDevice 의 16채널이 Event 하나를 공유한다. 기존 fire_power_clear_task 는 채널
1개가 정상복귀하면 `auto_resolve_active_events(prefix="power", device)` 로 디바이스
Event 를 통째 RESOLVE 했다. 아직 위험한 다른 채널의 Event 까지 닫히면, 다음 발화가
새 event_id 로 생성돼 프론트 60s dedup(event_id 키)을 통과 → 폭주.

가스는 `cleared_gases` 로 "event 의 가스가 전부 cleared 일 때만 RESOLVE" 하도록 이미
보호돼 있다. 본 테스트는 전력판 대응 — has_other_active_channel 게이팅으로
"다른 채널이 아직 위험하면 RESOLVE skip" 을 검증한다.
"""

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.alerts.models import AlarmRecord, Event
from apps.alerts.tasks import fire_power_clear_task
from apps.core.constants import AlarmType, EventStatus, RiskLevel
from apps.monitoring.services.power_alarm import _state_key, has_other_active_channel


@pytest.fixture
def no_ws_push(monkeypatch):
    """clear task 의 WS push 를 no-op 으로 — 테스트에서 fastapi HTTP 호출 회피."""
    monkeypatch.setattr("apps.alerts.tasks._push_to_ws", lambda *a, **k: None)


def _make_active_power_event(facility, power_device, channel):
    """ACTIVE 전력 Event + 해당 채널 AlarmRecord 1건 생성."""
    now = timezone.now()
    event = Event.objects.create(
        facility=facility,
        event_type=AlarmType.POWER_OVERLOAD,
        risk_level=RiskLevel.DANGER,
        status=EventStatus.ACTIVE,
        source_power_device=power_device,
        source_label=f"CH{channel}",
        summary="전력 과부하",
        first_detected_at=now,
        last_detected_at=now,
    )
    AlarmRecord.objects.create(
        facility=facility,
        event=event,
        alarm_type=AlarmType.POWER_OVERLOAD,
        power_device=power_device,
        channel=channel,
        risk_level=RiskLevel.DANGER,
        measured_value=4000.0,
    )
    return event


@pytest.mark.django_db
def test_clear_keeps_event_when_other_channel_active(
    facility, power_device, no_ws_push
):
    """ch2 정상복귀해도 ch3 가 위험이면 디바이스 Event 유지 (폭주 차단)."""
    cache.clear()
    event = _make_active_power_event(facility, power_device, channel=2)
    # ch3 아직 위험 — per-channel state 키 set (try_transition 이 운영에서 쓰는 키)
    cache.set(_state_key(power_device.id, 3), RiskLevel.DANGER, 60)

    fire_power_clear_task.apply(args=[power_device.id, 2, "CH2"]).get()

    event.refresh_from_db()
    assert event.status == EventStatus.ACTIVE  # RESOLVE 안 됨 — 다른 채널 위험 지속


@pytest.mark.django_db
def test_clear_resolves_event_when_last_channel(facility, power_device, no_ws_push):
    """다른 채널이 전부 정상이면 마지막 채널 정상복귀 시 Event RESOLVE."""
    cache.clear()
    event = _make_active_power_event(facility, power_device, channel=2)
    # 다른 채널 state 키 없음 (= 전부 정상)

    fire_power_clear_task.apply(args=[power_device.id, 2, "CH2"]).get()

    event.refresh_from_db()
    assert event.status == EventStatus.RESOLVED


@pytest.mark.django_db
def test_has_other_active_channel_helper(power_device):
    """헬퍼 단위 — exclude 채널 외 WARNING/DANGER 존재 여부."""
    cache.clear()
    # 아무 채널도 위험 아님 → False
    assert has_other_active_channel(power_device.id, 2) is False

    # ch5 WARNING → True (exclude 2 외 활성 채널 존재)
    cache.set(_state_key(power_device.id, 5), RiskLevel.WARNING, 60)
    assert has_other_active_channel(power_device.id, 2) is True

    # exclude 채널 자신만 위험하면 False (자기 자신은 제외)
    cache.clear()
    cache.set(_state_key(power_device.id, 2), RiskLevel.DANGER, 60)
    assert has_other_active_channel(power_device.id, 2) is False
