"""
지오펜스 진입 알람의 작업자별 dedup 회귀 가드.

create_alarm_and_event 의 병합 키는 발생원(센서/전력)은 source 단위지만, 지오펜스
진입은 작업자별 사건이다 — 같은 구역이라도 작업자가 다르면 별도 Event 로 분리한다
(event_service.py geofence 분기의 worker_id 필터). 이 계약이 깨지면 작업자 B 의 진입이
작업자 A 의 Event 에 흡수돼 "B 가 구역에 진입했다" 알람이 묻힌다.
"""

import pytest
from django.utils import timezone

from apps.alerts.models import Event
from apps.alerts.services.event_service import create_alarm_and_event
from apps.core.constants import AlarmType


@pytest.fixture
def geofence(db, facility):
    from apps.geofence.models import GeoFence

    return GeoFence.objects.create(
        facility=facility,
        name="작업자별 dedup 위험 구역",
        polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
        risk_level="warning",
    )


def _make_workers(count: int):
    from apps.accounts.models import CustomUser

    return [
        CustomUser.objects.create_user(
            username=f"dedup_worker_{i}",
            password="dedup-pass-1!",
            user_type="worker",
            name=f"dedup 작업자 {i}",
        )
        for i in range(count)
    ]


def _fire(facility, geofence, worker):
    return create_alarm_and_event(
        facility_id=facility.id,
        alarm_type=AlarmType.GEOFENCE_INTRUSION,
        geofence_id=geofence.id,
        worker_id=worker.id,
        risk_level="warning",
        source_label=geofence.name,
        summary=f"작업자 {worker.id} 진입",
        detected_at=timezone.now(),
    )


@pytest.mark.django_db
def test_different_workers_same_zone_create_separate_events(facility, geofence):
    """같은 위험구역이라도 작업자가 다르면 각각 독립 Event 가 생성된다."""
    worker_a, worker_b = _make_workers(2)

    event_a, alarm_a = _fire(facility, geofence, worker_a)
    event_b, alarm_b = _fire(facility, geofence, worker_b)

    assert event_a is not None and event_b is not None
    assert event_a.id != event_b.id  # 작업자별 분리
    assert event_a.worker_id == worker_a.id
    assert event_b.worker_id == worker_b.id
    assert Event.objects.filter(event_type=AlarmType.GEOFENCE_INTRUSION).count() == 2


@pytest.mark.django_db
def test_same_worker_same_zone_merges_into_one_event(facility, geofence):
    """같은 작업자가 같은 구역에 머물면 단일 Event 에 병합된다 (재발화 폭주 방지)."""
    (worker,) = _make_workers(1)

    event_first, _ = _fire(facility, geofence, worker)
    event_second, _ = _fire(facility, geofence, worker)

    assert event_first.id == event_second.id  # 동일 Event 병합
    assert Event.objects.filter(event_type=AlarmType.GEOFENCE_INTRUSION).count() == 1
