"""
지오펜스 알람 흐름 회귀 테스트 (Phase 1~4 회귀 점검 Step 3).

[회귀 커버 대상]
- Phase 3-a WorkerPosition.received_node FK (nullable, SET_NULL)
- handle_position_receive(node_id=...) lookup 흐름:
  - PositionNode 활성 상태일 때 → received_node 채움
  - PositionNode 비활성 또는 미존재 → received_node=None (silent fallback)
  - node_id=None (펌웨어 미갱신 row) → received_node=None
- 지오펜스 근접 시에만 WorkerPosition 저장

[설계 결정]
통합 테스트 — handle_position_receive() 진입점에서 PositionNode lookup + WorkerPosition
저장까지 검증. 외부 알람 task(fire_geofence_alarm_task)는 dangerous sensor 없을 때
호출 안 함을 검증.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.positioning.models import WorkerPosition
from apps.positioning.services.position_service import handle_position_receive


@pytest.fixture
def geofence(db, facility):
    """공장 (0,0)~(100,100) 영역의 위험 구역."""
    from apps.geofence.models import GeoFence

    return GeoFence.objects.create(
        facility=facility,
        name="회귀 점검 위험 구역",
        polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
        risk_level="warning",
    )


@pytest.mark.django_db
def test_position_with_valid_node_id_links_received_node(
    facility, worker_user, position_node, geofence
):
    """node_id 매칭되는 활성 PositionNode가 있으면 received_node FK로 연결."""
    result = handle_position_receive(
        worker_id=worker_user.id,
        facility_id=facility.id,
        x=50.0,  # geofence 내부
        y=50.0,
        movement_status="moving",
        measured_at=timezone.now(),
        node_id=position_node.device_id,
    )
    assert result["position_id"] is not None
    pos = WorkerPosition.objects.get(pk=result["position_id"])
    assert pos.received_node_id == position_node.id


@pytest.mark.django_db
def test_position_with_unknown_node_id_falls_back_to_none(
    facility, worker_user, geofence
):
    """node_id가 매칭 안 되면 silent fallback → received_node=None."""
    result = handle_position_receive(
        worker_id=worker_user.id,
        facility_id=facility.id,
        x=50.0,
        y=50.0,
        movement_status="moving",
        measured_at=timezone.now(),
        node_id="NODE-MISSING-999",
    )
    assert result["position_id"] is not None
    pos = WorkerPosition.objects.get(pk=result["position_id"])
    assert pos.received_node is None


@pytest.mark.django_db
def test_position_with_inactive_node_falls_back_to_none(
    facility, worker_user, position_node, geofence
):
    """비활성 PositionNode는 매칭 안 함 (silent fallback)."""
    position_node.deactivate()  # is_active=False
    result = handle_position_receive(
        worker_id=worker_user.id,
        facility_id=facility.id,
        x=50.0,
        y=50.0,
        movement_status="moving",
        measured_at=timezone.now(),
        node_id=position_node.device_id,
    )
    pos = WorkerPosition.objects.get(pk=result["position_id"])
    assert pos.received_node is None


@pytest.mark.django_db
def test_position_with_none_node_id_keeps_received_node_null(
    facility, worker_user, geofence
):
    """node_id=None (펌웨어 미갱신 row) → received_node=None."""
    result = handle_position_receive(
        worker_id=worker_user.id,
        facility_id=facility.id,
        x=50.0,
        y=50.0,
        movement_status="moving",
        measured_at=timezone.now(),
        node_id=None,
    )
    pos = WorkerPosition.objects.get(pk=result["position_id"])
    assert pos.received_node is None


@pytest.mark.django_db
def test_zone_risk_alone_fires_alarm_without_dangerous_sensor(
    facility, worker_user, geofence
):
    """센서 무관 구역(폴리곤 안에 센서 없음) 진입만으로 알람 발화.

    구역 안에 센서가 전혀 없으면 관리자가 지정한 정적 risk_level 로 발화한다.
    sensor_source_label 은 None (센서 임계치 초과 문구 없음).
    """
    with patch("apps.alerts.tasks.fire_geofence_alarm_task") as mock_task:
        result = handle_position_receive(
            worker_id=worker_user.id,
            facility_id=facility.id,
            x=50.0,  # warning 구역 내부, 구역 안에 센서 없음
            y=50.0,
            movement_status="moving",
            measured_at=timezone.now(),
            node_id=None,
        )

    assert result["risk_level"] == "warning"  # 구역 위험도가 risk_level 로 반영
    mock_task.delay.assert_called_once()
    kwargs = mock_task.delay.call_args.kwargs
    assert kwargs["risk_level"] == "warning"
    assert kwargs["geofence_id"] == geofence.id
    assert kwargs["worker_id"] == worker_user.id
    assert kwargs["sensor_source_label"] is None


@pytest.mark.django_db
def test_sensor_bound_zone_with_normal_sensor_does_not_fire(
    facility, worker_user, geofence, gas_sensor
):
    """센서 종속 구역(폴리곤 안에 센서 존재)은 센서 실시간 상태만 따른다.

    관리자가 구역을 warning 으로 지정했어도 안의 센서가 normal 이면 진입해도
    알람을 발화하지 않는다 — 정적 risk_level 이 센서 상태를 덮어쓰지 않게.
    """
    # gas_sensor 는 (10,20) 으로 geofence(0~100) 내부. GasData 미생성 → normal 취급.
    with patch("apps.alerts.tasks.fire_geofence_alarm_task") as mock_task:
        result = handle_position_receive(
            worker_id=worker_user.id,
            facility_id=facility.id,
            x=50.0,  # warning 구역 내부, 단 안의 센서가 normal
            y=50.0,
            movement_status="moving",
            measured_at=timezone.now(),
            node_id=None,
        )

    assert result["risk_level"] == "normal"  # 센서 normal → 정적 risk_level 무시
    mock_task.delay.assert_not_called()


@pytest.mark.django_db
def test_sensor_bound_zone_with_stale_danger_does_not_fire(
    facility, worker_user, geofence, gas_sensor
):
    """묵은 danger 측정값은 현재 위험으로 인정 안 함 (최신성 가드).

    더미/센서가 멈춘 뒤 마지막 danger 값이 DB에 남아도, freshness 윈도우(기본 60s)를
    넘으면 센서 정지로 보고 무시한다 — 진입해도 알람 미발화.
    """
    from apps.monitoring.models import GasData

    # GasData.save()는 raw 측정값으로 max_risk_level을 재계산하므로, create 후 update로
    # danger를 강제(저장 우회)해 위험 상태를 명시한다.
    gd = GasData.objects.create(
        gas_sensor=gas_sensor,
        measured_at=timezone.now() - timedelta(minutes=10),  # 윈도우(60s) 초과
    )
    GasData.objects.filter(pk=gd.pk).update(max_risk_level="danger")

    with patch("apps.alerts.tasks.fire_geofence_alarm_task") as mock_task:
        result = handle_position_receive(
            worker_id=worker_user.id,
            facility_id=facility.id,
            x=50.0,
            y=50.0,
            movement_status="moving",
            measured_at=timezone.now(),
            node_id=None,
        )

    assert result["risk_level"] == "normal"  # 묵은 danger → 무시
    mock_task.delay.assert_not_called()


@pytest.mark.django_db
def test_sensor_bound_zone_with_fresh_danger_fires(
    facility, worker_user, geofence, gas_sensor
):
    """최신 danger 측정값(윈도우 이내)은 정상적으로 진입 알람을 발화한다."""
    from apps.monitoring.models import GasData

    # save() 재계산 우회 — danger 강제 (위 stale 테스트와 동일 패턴).
    gd = GasData.objects.create(
        gas_sensor=gas_sensor,
        measured_at=timezone.now(),  # 방금 측정 — 윈도우 이내
    )
    GasData.objects.filter(pk=gd.pk).update(max_risk_level="danger")

    with patch("apps.alerts.tasks.fire_geofence_alarm_task") as mock_task:
        result = handle_position_receive(
            worker_id=worker_user.id,
            facility_id=facility.id,
            x=50.0,
            y=50.0,
            movement_status="moving",
            measured_at=timezone.now(),
            node_id=None,
        )

    assert result["risk_level"] == "danger"
    mock_task.delay.assert_called_once()
    kwargs = mock_task.delay.call_args.kwargs
    assert kwargs["risk_level"] == "danger"
    assert kwargs["sensor_source_label"] == gas_sensor.device_name


@pytest.mark.django_db
def test_position_far_from_geofence_saves_but_no_alarm(facility, worker_user, geofence):
    """지오펜스 밖이어도 위치는 항상 저장(이력 보존), 알람만 미발화.

    저장·알람 분리(handle_position_receive) — '근접 시에만 저장' 옛 계약은 폐기됐다.
    대부분 위치 이력이 유실돼 사고 소급 분석이 불가능해지기 때문. 근접 밖은 저장은
    하되 risk_level=normal 로 알람 판정만 건너뛴다.
    """
    result = handle_position_receive(
        worker_id=worker_user.id,
        facility_id=facility.id,
        x=500.0,  # geofence (0~100)에서 멀리
        y=500.0,
        movement_status="moving",
        measured_at=timezone.now(),
        node_id=None,
    )
    assert result["position_id"] is not None  # 항상 저장
    assert result["risk_level"] == "normal"  # 근접 밖 → 알람 판정 skip
    assert WorkerPosition.objects.count() == 1
