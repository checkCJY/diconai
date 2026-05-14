"""POST /alerts/api/anomaly-alarm-records/ 통합 테스트.

[검증 대상]
- 정상 INSERT + AlarmRecord/Event 생성 + ml_anomaly_result FK 사후 연결
- AlertPolicy 자동 매칭 (POWER_ANOMALY_AI 정책 row 등록 시)
- 발생원 lookup 실패 → 404
- enum 검증 → 400
- Event 자동 병합 (같은 device 짧은 간격 2회 호출 → AlarmRecord 2 + Event 1)

[가스 분기]
gas_anomaly_ai enum 미정의 — 가스 트랙 후속 sprint 에서 별도 테스트 추가.
"""

import pytest
from rest_framework.test import APIClient

from apps.alerts.models import AlarmRecord, AlertPolicy, Event
from apps.core.constants import AlarmType
from apps.ml.models import MLAnomalyResult

URL = "/alerts/api/anomaly-alarm-records/"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def ml_anomaly_row(db):
    return MLAnomalyResult.objects.create(
        ml_model=None,
        model_version_snapshot=3,
        sensor_type="power",
        sensor_identifier="power:device_1:ch1:watt",
        measured_at="2026-05-14T10:00:00Z",
        anomaly_score=-0.07,
        prediction=MLAnomalyResult.Prediction.ANOMALY,
        risk_classified=MLAnomalyResult.RiskClassified.PREDICT_WARN,
        feature_snapshot_json={"value": 8200},
    )


def _payload(power_device, ml_row=None):
    return {
        "alarm_type": "power_anomaly_ai",
        "risk_level": "warning",
        "source_device_id": power_device.device_id,
        "measured_value": 8200.0,
        "summary": "[AI 이상 패턴] CH1 watt=8200 (IF score -0.07)",
        "detected_at": "2026-05-14T10:00:00Z",
        "source_label": "CH1",
        "ml_anomaly_result_id": ml_row.id if ml_row else None,
    }


@pytest.mark.django_db
def test_create_anomaly_alarm_success(
    api_client, facility, power_device, ml_anomaly_row
):
    """정상 — 201 + AlarmRecord/Event 생성 + ml_anomaly_result FK 연결."""
    response = api_client.post(
        URL, _payload(power_device, ml_anomaly_row), format="json"
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["alarm_id"] is not None
    assert body["event_id"] is not None

    alarm = AlarmRecord.objects.get(id=body["alarm_id"])
    assert alarm.alarm_type == AlarmType.POWER_ANOMALY_AI
    assert alarm.power_device_id == power_device.id
    assert alarm.facility_id == facility.id
    assert alarm.ml_anomaly_result_id == ml_anomaly_row.id

    event = Event.objects.get(id=body["event_id"])
    assert event.event_type == AlarmType.POWER_ANOMALY_AI
    assert event.facility_id == facility.id


@pytest.mark.django_db
def test_create_anomaly_alarm_policy_matching(api_client, facility, power_device):
    """AlertPolicy 매칭 — POWER_ANOMALY_AI 정책 row 등록 시 Event.policy 자동 연결."""
    policy = AlertPolicy.objects.create(
        name="POWER_ANOMALY_AI default",
        event_type=AlarmType.POWER_ANOMALY_AI,
        target_facility=None,
    )

    response = api_client.post(URL, _payload(power_device), format="json")
    assert response.status_code == 201, response.content

    event = Event.objects.get(id=response.json()["event_id"])
    assert event.policy_id == policy.id


@pytest.mark.django_db
def test_create_anomaly_alarm_device_not_found(api_client, facility):
    """발생원 PowerDevice lookup 실패 → 404."""
    payload = {
        "alarm_type": "power_anomaly_ai",
        "risk_level": "warning",
        "source_device_id": "POW-DOES-NOT-EXIST",
        "summary": "test",
        "detected_at": "2026-05-14T10:00:00Z",
        "source_label": "CH1",
    }
    response = api_client.post(URL, payload, format="json")
    assert response.status_code == 404
    assert AlarmRecord.objects.count() == 0
    assert Event.objects.count() == 0


@pytest.mark.django_db
def test_create_anomaly_alarm_invalid_alarm_type(api_client, power_device):
    """잘못된 alarm_type → 400."""
    payload = _payload(power_device)
    payload["alarm_type"] = "gas_anomaly_ai"  # 현재 sprint serializer 미허용
    response = api_client.post(URL, payload, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_create_anomaly_alarm_event_merge(api_client, facility, power_device):
    """Event 자동 병합 — 같은 device 짧은 간격 2회 호출 → AlarmRecord 2 + Event 1."""
    r1 = api_client.post(URL, _payload(power_device), format="json")
    assert r1.status_code == 201
    r2 = api_client.post(URL, _payload(power_device), format="json")
    assert r2.status_code == 201

    alarms = AlarmRecord.objects.filter(power_device_id=power_device.id)
    assert alarms.count() == 2
    events = Event.objects.filter(
        facility_id=facility.id, event_type=AlarmType.POWER_ANOMALY_AI
    )
    assert events.count() == 1
    # 두 alarm 이 같은 event 에 묶임
    assert {a.event_id for a in alarms} == {events.first().id}
