"""
가스 알람 흐름 회귀 테스트 (Phase 1~4 회귀 점검 Step 3).

[회귀 커버 대상]
- Phase 4-c GasData.save() 단일 진실 공급원: raw 측정값으로부터 *_risk 9종 + max_risk_level
  자동 재계산. fastapi 페이로드의 *_risk 필드는 무시됨 (DB Threshold가 마스터).
- O2 분기 (낮을수록 위험)
- 미측정 가스(None)는 *_risk도 None 유지
- threshold_default fixture (gas_legal 9종) DB 시드 의존

[설계 결정]
통합 테스트 — GasData.save() → recalculate_risks_from_thresholds() →
threshold_service.evaluate_gas_risk() → DB Threshold 조회 체인 전체 검증.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.constants import RiskLevel
from apps.monitoring.models import GasData


@pytest.fixture
def now():
    return timezone.now()


@pytest.mark.django_db
def test_gas_data_save_recalculates_risks_from_raw(gas_sensor, now):
    """raw 측정값만으로 *_risk 9종이 DB Threshold 기반 재계산되는지."""
    data = GasData.objects.create(
        gas_sensor=gas_sensor,
        co=10.0,  # < 25 (warning_max) → normal
        h2s=12.0,  # > 10 (warning_max), < 15 (danger_max) → warning
        co2=200.0,  # < 1000 → normal
        o2=20.0,  # 18 ~ 23.5 사이 → normal
        no2=10.0,  # > 5 (danger_max) → danger
        so2=1.0,
        o3=0.01,
        nh3=10.0,
        voc=0.1,
        measured_at=now - timedelta(seconds=1),
    )
    assert data.co_risk == RiskLevel.NORMAL
    assert data.h2s_risk == RiskLevel.WARNING
    assert data.co2_risk == RiskLevel.NORMAL
    assert data.o2_risk == RiskLevel.NORMAL
    assert data.no2_risk == RiskLevel.DANGER
    # max_risk_level 캐시 — 가장 높은 위험도 반영
    assert data.max_risk_level == RiskLevel.DANGER


@pytest.mark.django_db
def test_payload_risk_is_ignored_single_source_of_truth(gas_sensor, now):
    """페이로드에 잘못된 *_risk가 들어와도 DB 기반 재계산이 우선."""
    # 페이로드가 co=200(=danger 영역) 측정값을 보내면서
    # co_risk="normal"이라고 잘못 주장 → save() 시 DB로 재계산되어 danger로 정정됨
    data = GasData(
        gas_sensor=gas_sensor,
        co=200.0,  # >= danger_max=200 → danger
        co_risk=RiskLevel.NORMAL,  # 페이로드의 잘못된 주장
        measured_at=now,
    )
    data.save()
    data.refresh_from_db()
    assert data.co_risk == RiskLevel.DANGER
    assert data.max_risk_level == RiskLevel.DANGER


@pytest.mark.django_db
def test_o2_below_danger_min_marks_danger(gas_sensor, now):
    """O2는 낮을수록 위험. danger_min=16 미만이면 danger."""
    data = GasData.objects.create(
        gas_sensor=gas_sensor,
        o2=15.0,  # < 16 → danger
        measured_at=now,
    )
    assert data.o2_risk == RiskLevel.DANGER
    assert data.max_risk_level == RiskLevel.DANGER


@pytest.mark.django_db
def test_o2_between_warning_and_danger_marks_warning(gas_sensor, now):
    """O2가 warning_min=18 미만 + danger_min=16 이상이면 warning."""
    data = GasData.objects.create(
        gas_sensor=gas_sensor,
        o2=17.0,
        measured_at=now,
    )
    assert data.o2_risk == RiskLevel.WARNING


@pytest.mark.django_db
def test_missing_gas_keeps_risk_none(gas_sensor, now):
    """미측정(None) 가스는 *_risk도 None 유지 (오인 판정 회피)."""
    data = GasData.objects.create(
        gas_sensor=gas_sensor,
        co=10.0,
        h2s=None,  # 미측정
        measured_at=now,
    )
    assert data.co_risk == RiskLevel.NORMAL
    assert data.h2s_risk is None
    # max_risk_level은 valid risk 중 최고
    assert data.max_risk_level == RiskLevel.NORMAL


@pytest.mark.django_db
def test_all_missing_gas_max_risk_normal(gas_sensor, now):
    """모든 가스 None이면 max_risk_level=normal (default)."""
    data = GasData.objects.create(
        gas_sensor=gas_sensor,
        measured_at=now,
    )
    assert data.max_risk_level == RiskLevel.NORMAL
