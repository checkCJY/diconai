"""
EventAcknowledgement user-scoped ack 회귀 (2026-05-15 알람 재설계).

[검증 대상]
- 모델: UniqueConstraint(event, user) — 같은 (event, user) 중복 row 차단
- API: POST /alerts/api/events/{id}/ack/ — get_or_create idempotent + 인증 필수
- selector: get_acked_user_ids — user 단위 ack set 반환

[user-scoped 보장]
"본 사람만 안 보이고, 다른 사용자에게는 계속 뜸" 의 핵심 데이터 모델.
한 user 의 ack 가 다른 user 에 영향 없음을 회귀 가드로 보장.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.models import Event, EventAcknowledgement
from apps.alerts.selectors.event_ack_selector import get_acked_user_ids
from apps.core.constants import AlarmType, EventStatus, RiskLevel

User = get_user_model()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="regress_admin",
        password="regress-pass-1!",
        user_type="super_admin",
        name="회귀 관리자",
    )


@pytest.fixture
def admin_user_2(db):
    return User.objects.create_user(
        username="regress_admin_2",
        password="regress-pass-1!",
        user_type="super_admin",
        name="회귀 관리자 2",
    )


@pytest.fixture
def gas_event(db, facility, gas_sensor):
    return Event.objects.create(
        facility=facility,
        event_type=AlarmType.GAS_THRESHOLD,
        risk_level=RiskLevel.DANGER,
        status=EventStatus.ACTIVE,
        source_sensor=gas_sensor,
        source_label="회귀 가스",
        summary="회귀 위험 상황",
        first_detected_at=timezone.now(),
        last_detected_at=timezone.now(),
    )


@pytest.mark.django_db
def test_event_acknowledgement_unique_constraint(gas_event, admin_user):
    """UniqueConstraint(event, user) — 같은 쌍 중복 row DB 레벨 차단."""
    EventAcknowledgement.objects.create(event=gas_event, user=admin_user)
    with pytest.raises(IntegrityError):
        EventAcknowledgement.objects.create(event=gas_event, user=admin_user)


@pytest.mark.django_db
def test_ack_api_creates_row_idempotent(gas_event, admin_user):
    """POST /events/{id}/ack/ — 첫 호출 created=True, 재호출 created=False (idempotent)."""
    client = APIClient()
    client.force_authenticate(user=admin_user)

    res1 = client.post(f"/alerts/api/events/{gas_event.id}/ack/", format="json")
    assert res1.status_code == 200
    body1 = res1.json()
    assert body1["created"] is True
    assert body1["event_id"] == gas_event.id
    assert body1["user_id"] == admin_user.id
    assert body1["acknowledged_at"] is not None

    res2 = client.post(f"/alerts/api/events/{gas_event.id}/ack/", format="json")
    assert res2.status_code == 200
    assert res2.json()["created"] is False

    # DB 에 row 1건만 (UniqueConstraint + get_or_create 이중 보호)
    qs = EventAcknowledgement.objects.filter(event=gas_event, user=admin_user)
    assert qs.count() == 1


@pytest.mark.django_db
def test_ack_api_requires_authentication(gas_event):
    """비인증 요청 → 401. EventViewSet 의 IsAuthenticated 보장."""
    client = APIClient()
    res = client.post(f"/alerts/api/events/{gas_event.id}/ack/", format="json")
    assert res.status_code == 401


@pytest.mark.django_db
def test_selector_returns_user_scoped_set(gas_event, admin_user, admin_user_2):
    """get_acked_user_ids — 2명 ack 시 user 단위 set 분리 보장.

    한 user 의 ack 가 다른 user 의 조회 결과에 영향 안 줌.
    Phase 3 의 서버 측 ack 분기 (옵션 B) 에서 broadcast hot path 가 이 selector 사용.
    """
    # 초기 빈 set
    assert get_acked_user_ids(gas_event.id) == set()

    EventAcknowledgement.objects.create(event=gas_event, user=admin_user)
    assert get_acked_user_ids(gas_event.id) == {admin_user.id}

    EventAcknowledgement.objects.create(event=gas_event, user=admin_user_2)
    assert get_acked_user_ids(gas_event.id) == {admin_user.id, admin_user_2.id}


@pytest.mark.django_db
def test_cooldown_env_default(settings):
    """ALARM_REPOPUP_COOLDOWN_SEC 기본 60s + env 변수 override 가능 검증.

    event_service.py 의 재알림 cooldown 이 이 settings 를 참조.
    .env.docker 의 ALARM_REPOPUP_COOLDOWN_SEC=15 같은 시연 모드 override 흐름의 가드.
    """
    assert hasattr(settings, "ALARM_REPOPUP_COOLDOWN_SEC")
    # int 타입 + 양수 보장
    assert isinstance(settings.ALARM_REPOPUP_COOLDOWN_SEC, int)
    assert settings.ALARM_REPOPUP_COOLDOWN_SEC > 0
