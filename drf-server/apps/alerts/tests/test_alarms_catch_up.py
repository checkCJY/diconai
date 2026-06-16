"""
GET /alerts/api/alarms/catch-up/?since= WS 재연결 catch-up 회귀 (2026-05-15).

[검증 대상]
- since 이후 알람만 반환 (이전은 제외)
- 24h 이상 과거 since 는 24h 까지 클램프
- 응답 모양 = fastapi broadcast payload (alarm_type/risk_level/source_label/...)
- since 누락/잘못된 값 → 빈 list (early return — 안전)

[흐름]
클라 alarm-popup.js 의 _runCatchUp() 가 localStorage 의 last_seen_ts 를 since 로 전달.
WS 끊김 중 알람 보충용 — 시연 PC 일시 끊김에 대한 안전망.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.models import AlarmRecord, Event
from apps.core.constants import AlarmType, EventStatus, RiskLevel

User = get_user_model()

URL = "/alerts/api/alarms/catch-up/"


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="regress_admin",
        password="regress-pass-1!",
        user_type="super_admin",
        name="회귀 관리자",
    )


def _make_alarm(facility, gas_sensor, created_at):
    """주어진 created_at 으로 AlarmRecord 1건 생성 (Event 자동 1건 동반).

    AlarmRecord.created_at 은 auto_now_add 라 직접 set 불가 → 생성 후 update 로 강제.
    """
    event = Event.objects.create(
        facility=facility,
        event_type=AlarmType.GAS_THRESHOLD,
        risk_level=RiskLevel.DANGER,
        status=EventStatus.ACTIVE,
        source_sensor=gas_sensor,
        source_label="회귀 가스",
        summary="회귀 위험",
        first_detected_at=created_at,
        last_detected_at=created_at,
    )
    alarm = AlarmRecord.objects.create(
        facility=facility,
        event=event,
        alarm_type=AlarmType.GAS_THRESHOLD,
        sensor=gas_sensor,
        gas_type="co",
        measured_value=250.0,
        threshold_value=200.0,
        risk_level=RiskLevel.DANGER,
    )
    # auto_now_add 우회 — 시간 기반 필터링 검증에 필수
    AlarmRecord.objects.filter(id=alarm.id).update(created_at=created_at)
    return alarm


@pytest.mark.django_db
def test_catch_up_returns_alarms_after_since(facility, gas_sensor, admin_user):
    """since 이후 알람만 반환 — since 이전 알람은 응답에서 제외."""
    now = timezone.now()
    _make_alarm(facility, gas_sensor, now - timedelta(minutes=30))  # since 이후 (포함)
    _make_alarm(facility, gas_sensor, now - timedelta(minutes=10))  # since 이후 (포함)
    _make_alarm(facility, gas_sensor, now - timedelta(hours=2))  # since 이전 (제외)

    since_ts = (now - timedelta(hours=1)).timestamp()
    client = APIClient()
    client.force_authenticate(user=admin_user)
    res = client.get(f"{URL}?since={since_ts}")

    assert res.status_code == 200
    alarms = res.json()["alarms"]
    assert len(alarms) == 2


@pytest.mark.django_db
def test_catch_up_clamps_to_24h(facility, gas_sensor, admin_user):
    """since 가 24h 이상 과거여도 24h 까지로 클램프 — 너무 오래된 알람은 의미 없음."""
    now = timezone.now()
    _make_alarm(facility, gas_sensor, now - timedelta(hours=25))  # 24h 밖 (제외)
    _make_alarm(facility, gas_sensor, now - timedelta(hours=10))  # 24h 안 (포함)

    since_ts = (now - timedelta(hours=30)).timestamp()  # 30시간 전 → 24h 로 클램프
    client = APIClient()
    client.force_authenticate(user=admin_user)
    res = client.get(f"{URL}?since={since_ts}")

    assert res.status_code == 200
    assert len(res.json()["alarms"]) == 1


@pytest.mark.django_db
def test_catch_up_returns_broadcast_payload_shape(facility, gas_sensor, admin_user):
    """응답 모양 = fastapi broadcast payload 와 키 일관 — 클라 측 mapper 공용 처리 가능."""
    now = timezone.now()
    _make_alarm(facility, gas_sensor, now - timedelta(minutes=5))

    since_ts = (now - timedelta(minutes=10)).timestamp()
    client = APIClient()
    client.force_authenticate(user=admin_user)
    res = client.get(f"{URL}?since={since_ts}")

    assert res.status_code == 200
    alarm = res.json()["alarms"][0]
    expected_keys = {
        "event_id",
        "alarm_type",
        "risk_level",
        "source_label",
        "summary",
        "message",
        "is_new_event",
        "created_at",
    }
    assert expected_keys.issubset(set(alarm.keys()))
    # catch-up 으로 들어온 알람은 절대 새 알람 아님 — 팝업 자연 skip 기준
    assert alarm["is_new_event"] is False


@pytest.mark.django_db
def test_catch_up_missing_since_returns_empty(admin_user):
    """since 쿼리 누락 → 빈 list (서버 early return)."""
    client = APIClient()
    client.force_authenticate(user=admin_user)
    res = client.get(URL)
    assert res.status_code == 200
    assert res.json() == {"alarms": []}


@pytest.mark.django_db
def test_catch_up_invalid_since_returns_empty(admin_user):
    """잘못된 since (숫자 아님) → 빈 list (조용히 fallback, 500 아님)."""
    client = APIClient()
    client.force_authenticate(user=admin_user)
    res = client.get(f"{URL}?since=not-a-number")
    assert res.status_code == 200
    assert res.json() == {"alarms": []}


@pytest.mark.django_db
def test_catch_up_caps_at_100(facility, gas_sensor, admin_user):
    """응답 최대 100건 상한 — race 패킷 폭주 방지."""
    now = timezone.now()
    # 105건 생성, 모두 since 이후
    for i in range(105):
        _make_alarm(facility, gas_sensor, now - timedelta(minutes=i + 1))

    since_ts = (now - timedelta(hours=23)).timestamp()
    client = APIClient()
    client.force_authenticate(user=admin_user)
    res = client.get(f"{URL}?since={since_ts}")

    assert res.status_code == 200
    assert len(res.json()["alarms"]) == 100
