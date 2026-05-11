"""
e2e 알람 흐름 통합 테스트 (PR-H).

[목적]
PR-C AlertPolicy 시드 + PR-G facility 우선순위가 적용된 후, fire_*_alarm_task →
create_alarm_and_event → policy 매칭 → AlarmRecord/Event 생성 흐름을 e2e로 검증.

[설계]
- Celery task를 `.apply(args=..., kwargs=...)`로 동기 실행 (worker 미가동 OK)
- `_push_to_ws` mock으로 WS broadcast / IntegrationLog Celery delay() 무력화
- AlertPolicy 시드는 PR-C 마이그가 자동 시드 — 별도 fixture 불필요

[회귀 커버]
- 가스: fire_danger_alarm_task → AlarmRecord + Event + Event.policy=gas_threshold seed
- 전력: fire_power_danger_task → AlarmRecord + Event + Event.policy=power_overload seed
- 지오펜스: fire_geofence_alarm_task → AlarmRecord + Event + Event.policy=geofence_intrusion seed
- 안전 체크리스트는 알람 task 미발생 (정상 흐름) — Step 3 test_check_item_flow.py 5건으로 검증 완료
"""

from unittest.mock import patch

import pytest

from apps.alerts.models import AlarmRecord, AlertPolicy, Event
from apps.core.constants import AlarmType


@pytest.fixture(autouse=True)
def mock_push_to_ws():
    """WS broadcast 호출 차단 (httpx.post + IntegrationLog Celery delay)."""
    with patch("apps.alerts.tasks._push_to_ws") as m:
        yield m


@pytest.mark.django_db
def test_gas_alarm_e2e_creates_event_with_policy(facility, gas_sensor):
    """가스 e2e: fire_danger_alarm_task → AlarmRecord/Event 생성, policy 매칭."""
    from apps.alerts.tasks import fire_danger_alarm_task

    # PR-C에서 시드된 gas_threshold 정책 존재 확인
    seed_policy = AlertPolicy.objects.filter(
        event_type=AlarmType.GAS_THRESHOLD, target_facility=None
    ).first()
    assert seed_policy is not None, "PR-C 시드 정책 부재"

    fire_danger_alarm_task.apply(
        kwargs={
            "sensor_id": gas_sensor.id,
            "gas_type": "co",
            "value": 250.0,
            "facility_id": facility.id,
            "source_label": gas_sensor.device_name,
        }
    )

    # AlarmRecord 1건 생성
    alarms = AlarmRecord.objects.filter(sensor_id=gas_sensor.id)
    assert alarms.count() == 1
    assert alarms.first().alarm_type == AlarmType.GAS_THRESHOLD

    # Event 1건 생성, policy 매칭 (PR-C seed)
    events = Event.objects.filter(facility=facility, event_type=AlarmType.GAS_THRESHOLD)
    assert events.count() == 1
    assert events.first().policy_id == seed_policy.id


@pytest.mark.django_db
def test_power_alarm_e2e_creates_event_with_policy(facility, power_device):
    """전력 e2e: fire_power_danger_task → AlarmRecord/Event 생성, policy 매칭."""
    from apps.alerts.tasks import fire_power_danger_task

    seed_policy = AlertPolicy.objects.filter(
        event_type=AlarmType.POWER_OVERLOAD, target_facility=None
    ).first()
    assert seed_policy is not None

    fire_power_danger_task.apply(
        kwargs={
            "device_id": power_device.id,
            "channel": 1,
            "value": 3000.0,
            "facility_id": facility.id,
            "source_label": power_device.device_name,
        }
    )

    alarms = AlarmRecord.objects.filter(power_device_id=power_device.id)
    assert alarms.count() == 1
    assert alarms.first().alarm_type == AlarmType.POWER_OVERLOAD

    events = Event.objects.filter(
        facility=facility, event_type=AlarmType.POWER_OVERLOAD
    )
    assert events.count() == 1
    assert events.first().policy_id == seed_policy.id


@pytest.fixture
def geofence(db, facility):
    from apps.geofence.models import GeoFence

    return GeoFence.objects.create(
        facility=facility,
        name="e2e 위험 구역",
        polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
        risk_level="warning",
    )


@pytest.mark.django_db
def test_geofence_alarm_e2e_creates_event_with_policy(facility, worker_user, geofence):
    """지오펜스 e2e: fire_geofence_alarm_task → AlarmRecord/Event 생성, policy 매칭."""
    from apps.alerts.tasks import fire_geofence_alarm_task

    seed_policy = AlertPolicy.objects.filter(
        event_type=AlarmType.GEOFENCE_INTRUSION, target_facility=None
    ).first()
    assert seed_policy is not None

    fire_geofence_alarm_task.apply(
        kwargs={
            "worker_id": worker_user.id,
            "facility_id": facility.id,
            "geofence_id": geofence.id,
            "geofence_name": geofence.name,
            "risk_level": "danger",
            "sensor_source_label": "테스트 센서",
        }
    )

    alarms = AlarmRecord.objects.filter(geofence_id=geofence.id)
    assert alarms.count() == 1
    assert alarms.first().alarm_type == AlarmType.GEOFENCE_INTRUSION

    events = Event.objects.filter(
        facility=facility, event_type=AlarmType.GEOFENCE_INTRUSION
    )
    assert events.count() == 1
    assert events.first().policy_id == seed_policy.id


@pytest.mark.django_db
def test_safety_check_normal_flow_no_alarm(facility, worker_user):
    """안전 체크리스트 e2e: 정상 체크 흐름 — 알람 발생 0건 (회귀 가드)."""
    from apps.safety.models import (
        SafetyCheckItem,
        SafetyChecklistRevision,
        SafetyCheckSection,
    )
    from apps.safety.services.check_service import check_item

    section = SafetyCheckSection.objects.create(
        facility=facility, name="e2e 섹션", order=1
    )
    SafetyChecklistRevision.objects.create(
        facility=facility, version=1, is_active=True, revision_data={"sections": []}
    )
    item = SafetyCheckItem.objects.create(
        facility=facility, section=section, title="안전모", order=1, is_required=True
    )

    # 정상 흐름 (알람 미발생)
    status = check_item(worker_id=worker_user.id, item_id=item.id, note="OK")
    assert status.is_checked is True

    # 알람 발생 0건 — 안전 체크리스트는 미완료 시에만 알람 (PR-C ppe_violation/safety_check_pending
    # 정책은 별도 task에서 트리거. 본 흐름은 정상 체크 → 알람 0건)
    assert AlarmRecord.objects.count() == 0
    assert Event.objects.count() == 0
