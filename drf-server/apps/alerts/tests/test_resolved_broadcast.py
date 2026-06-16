"""
update_status RESOLVED 분기 시 _push_to_ws 호출 + event_resolved_at 박힘 회귀 (2026-05-15).

[검증 대상]
- PATCH /alerts/api/events/{id}/update_status/ status=resolved →
  apps.alerts.tasks._push_to_ws 호출 (raise_on_failure=False)
- payload 에 event_resolved_at (ISO string), event_id, is_new_event=False 박힘
- 다른 상태 전환 (ACKNOWLEDGED, IN_PROGRESS) 시는 _push_to_ws 미호출 — surgical 보장

[전체 흐름 가드]
운영자 RESOLVED 클릭 → drf push → fastapi → broadcast → 클라 _handleResolved
경로의 백엔드 측 시작점 검증. 클라 측은 브라우저 수동 검증 + Phase 2 cypress 후속.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.models import Event
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
def active_event(db, facility, gas_sensor):
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
def test_update_status_resolved_pushes_event_resolved_at(active_event, admin_user):
    """ACTIVE → RESOLVED → _push_to_ws 가 event_resolved_at 박은 payload 로 호출."""
    client = APIClient()
    client.force_authenticate(user=admin_user)

    with patch("apps.alerts.tasks._push_to_ws") as push_mock:
        res = client.patch(
            f"/alerts/api/events/{active_event.id}/update_status/",
            {"status": "resolved"},
            format="json",
        )

    assert res.status_code == 200
    push_mock.assert_called_once()

    # call_args 는 (args, kwargs). 첫 인자가 payload dict.
    args, kwargs = push_mock.call_args
    payload = args[0]
    assert payload["event_id"] == active_event.id
    assert payload["event_resolved_at"] is not None
    assert payload["is_new_event"] is False
    assert payload["alarm_type"] == AlarmType.GAS_THRESHOLD
    # WS 푸시 실패가 트랜잭션 망치지 않도록 raise_on_failure=False
    assert kwargs.get("raise_on_failure") is False


@pytest.mark.django_db
def test_update_status_acknowledged_does_not_push(active_event, admin_user):
    """ACTIVE → ACKNOWLEDGED 전환은 _push_to_ws 호출 안 함 (surgical)."""
    client = APIClient()
    client.force_authenticate(user=admin_user)

    with patch("apps.alerts.tasks._push_to_ws") as push_mock:
        res = client.patch(
            f"/alerts/api/events/{active_event.id}/update_status/",
            {"status": "acknowledged"},
            format="json",
        )

    assert res.status_code == 200
    push_mock.assert_not_called()


@pytest.mark.django_db
def test_update_status_in_progress_does_not_push(active_event, admin_user):
    """ACTIVE → IN_PROGRESS 전환은 _push_to_ws 호출 안 함."""
    client = APIClient()
    client.force_authenticate(user=admin_user)

    with patch("apps.alerts.tasks._push_to_ws") as push_mock:
        res = client.patch(
            f"/alerts/api/events/{active_event.id}/update_status/",
            {"status": "in_progress"},
            format="json",
        )

    assert res.status_code == 200
    push_mock.assert_not_called()
