"""
Event 알림의 on_commit 지연·롤백 안전성 회귀 가드 (P0 신규).

create_alarm_and_event 는 Notification 발송(_notify_safe)을 transaction.on_commit
으로 지연한다 — 롤백될 수 있는 Event 를 Notification 이 참조하는 상황을 막기 위함
(event_service.py L210-213). 이 계약이 깨지면 롤백된 알람에 대해 사용자에게 유령
알림이 발송되거나, 미커밋 Event 를 참조해 무결성이 깨진다.
"""

from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone

from apps.alerts.models import Event
from apps.core.constants import AlarmType

_NOTIFY_PATH = "apps.notifications.services.notification_service.notify_event_created"


def _make_gas_alarm(facility, gas_sensor):
    """신규 가스 DANGER 알람 1건 — 활성 Event 부재 → 새 Event 생성 경로 진입."""
    from apps.alerts.services.event_service import create_alarm_and_event

    return create_alarm_and_event(
        facility_id=facility.id,
        alarm_type=AlarmType.GAS_THRESHOLD,
        sensor_id=gas_sensor.id,
        gas_type="co",
        measured_value=120.0,
        threshold_value=50.0,
        risk_level="danger",
        source_label="테스트 센서",
        summary="가스 위험",
        detected_at=timezone.now(),
    )


@pytest.mark.django_db
def test_notification_deferred_until_commit(
    facility, gas_sensor, django_capture_on_commit_callbacks
):
    """알림은 함수 실행 중이 아니라 트랜잭션 커밋 후에만 발송된다."""
    with patch(_NOTIFY_PATH) as mock_notify:
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            event, alarm = _make_gas_alarm(facility, gas_sensor)
            assert event is not None and alarm is not None
            # 커밋 전 — 아직 미발송 (on_commit 으로 지연됨)
            mock_notify.assert_not_called()
        # with 블록 종료 = 커밋 시뮬레이션 → on_commit 콜백 1개 실행 → 발송
        assert len(callbacks) == 1
        mock_notify.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_notification_not_sent_on_rollback(facility, gas_sensor):
    """외부 트랜잭션 롤백 시 알림 미발송 + Event 미생성 (on_commit 콜백 폐기).

    transaction=True 라 바깥 atomic 이 최외곽 트랜잭션 — 실제 커밋/롤백 의미가 산다.
    바깥에서 예외로 롤백하면 안에서 등록한 on_commit 콜백은 폐기되고 Event 도 사라진다.
    """
    with patch(_NOTIFY_PATH) as mock_notify:
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                _make_gas_alarm(facility, gas_sensor)
                raise RuntimeError("강제 롤백")

        mock_notify.assert_not_called()
        assert Event.objects.count() == 0
