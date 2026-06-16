# 이성현 수정 — 주석 보강 및 PG 호환 확인
# PR-C 마이그레이션 시드(AlertPolicy 9종)에 의존 — PG 환경에서 마이그레이션 실행 시 자동 생성됨.
# Celery task는 .apply()로 동기 실행 → worker 없이도 테스트 가능.
# _push_to_ws mock → WebSocket broadcast / IntegrationLog Celery delay() 차단.
from unittest.mock import patch

import pytest

from apps.alerts.models import AlarmRecord, AlertPolicy, Event
from apps.core.constants import AlarmType


@pytest.fixture(autouse=True)
def mock_push_to_ws():
    # WS broadcast는 외부 서비스(FastAPI) 호출이 필요하므로 테스트 중 차단.
    # mock으로 대체해 실제 HTTP 요청 없이 알람 생성 흐름만 검증.
    with patch("apps.alerts.tasks._push_to_ws") as m:
        yield m


@pytest.mark.django_db
def test_gas_alarm_e2e_creates_event_with_policy(facility, gas_sensor):
    """가스 알람 태스크 실행 → AlarmRecord·Event 1건 생성·시드 정책 연결 확인."""
    # 가스 위험 알람 태스크 실행 시 AlarmRecord + Event가 정상 생성되는지 확인.
    # PR-C 시드 정책(gas_threshold, 전사)이 PG에도 존재하는지도 함께 검증.
    from apps.alerts.tasks import fire_danger_alarm_task

    seed_policy = AlertPolicy.objects.filter(
        event_type=AlarmType.GAS_THRESHOLD, target_facility=None
    ).first()
    assert seed_policy is not None, "PR-C 시드 정책 부재 — 마이그레이션 확인 필요"

    fire_danger_alarm_task.apply(
        kwargs={
            "sensor_id": gas_sensor.id,
            "gas_type": "co",
            "value": 250.0,
            "facility_id": facility.id,
            "source_label": gas_sensor.device_name,
        }
    )

    # AlarmRecord 1건 생성 확인
    alarms = AlarmRecord.objects.filter(sensor_id=gas_sensor.id)
    assert alarms.count() == 1
    assert alarms.first().alarm_type == AlarmType.GAS_THRESHOLD

    # Event 1건 생성 + PR-C 시드 정책 연결 확인
    events = Event.objects.filter(facility=facility, event_type=AlarmType.GAS_THRESHOLD)
    assert events.count() == 1
    assert events.first().policy_id == seed_policy.id


@pytest.mark.django_db
def test_power_alarm_e2e_creates_event_with_policy(facility, power_device):
    """전력 과부하 알람 태스크 실행 → AlarmRecord·Event 1건 생성·시드 정책 연결 확인."""
    # 전력 과부하 알람 태스크 실행 시 AlarmRecord + Event 생성 확인.
    from apps.alerts.tasks import fire_power_danger_task

    seed_policy = AlertPolicy.objects.filter(
        event_type=AlarmType.POWER_OVERLOAD, target_facility=None
    ).first()
    assert seed_policy is not None, "PR-C 시드 정책 부재 — 마이그레이션 확인 필요"

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
    # 테스트용 위험 구역 — (0,0)~(100,100) 사각형 영역.
    from apps.geofence.models import GeoFence

    return GeoFence.objects.create(
        facility=facility,
        name="e2e 위험 구역",
        polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
        risk_level="warning",
    )


@pytest.mark.django_db
def test_geofence_alarm_e2e_creates_event_with_policy(facility, worker_user, geofence):
    """지오펜스 진입 알람 태스크 실행 → AlarmRecord·Event 1건 생성·시드 정책 연결 확인."""
    # 작업자가 위험구역 진입 시 AlarmRecord + Event 생성 확인.
    from apps.alerts.tasks import fire_geofence_alarm_task

    seed_policy = AlertPolicy.objects.filter(
        event_type=AlarmType.GEOFENCE_INTRUSION, target_facility=None
    ).first()
    assert seed_policy is not None, "PR-C 시드 정책 부재 — 마이그레이션 확인 필요"

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
    """안전 체크 정상 완료 시 AlarmRecord·Event 0건 확인."""
    # 안전 체크리스트 정상 체크 시 알람이 발생하지 않는지 확인.
    # 알람은 미완료 상태일 때만 발생 — 정상 체크 흐름은 알람 0건이어야 함.
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

    status = check_item(worker_id=worker_user.id, item_id=item.id, note="OK")
    assert status.is_checked is True

    # 정상 체크 후 알람 0건 확인
    assert AlarmRecord.objects.count() == 0
    assert Event.objects.count() == 0
