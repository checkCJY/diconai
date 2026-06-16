# 이성현 수정 — Redis 캐시 의존 제거 (PostgreSQL + CI 호환)
# cache.clear() 직접 호출 제거 → conftest.py의 use_dummy_cache fixture가 자동 처리.
import pytest
from rest_framework.test import APIRequestFactory

from apps.core.constants import RiskLevel
from apps.facilities.services.threshold_service import (
    evaluate_power_risk,
    get_threshold,
    invalidate_threshold_cache,
)


@pytest.mark.django_db
def test_get_threshold_returns_chart_max(db):
    """power_default/power_w 시드 임계값(warning 2200·danger 2860·chart 3500·W) 확인."""
    # 마이그레이션 시드(power_default/power_w)가 PG에도 정상 존재하는지 확인.
    # warning_max=2200, danger_max=2860, chart_max=3500 은 운영 기준값.
    threshold = get_threshold("power_default", "power_w")
    assert threshold is not None
    assert threshold["warning_max"] == 2200
    assert threshold["danger_max"] == 2860
    assert threshold["chart_max"] == 3500
    assert threshold["unit"] == "W"


@pytest.mark.django_db
def test_evaluate_power_risk_normal_warning_danger(db):
    """watt 값별 NORMAL/WARNING/DANGER 경계값 분기 및 None → NORMAL fallback 검증."""
    # DB 기반 위험도 분기 검증.
    # 2200 이하 → 정상, 2200 초과~2860 이하 → 경고, 2860 초과 → 위험.
    invalidate_threshold_cache("power_default", "power_w")
    assert evaluate_power_risk(1000) == RiskLevel.NORMAL
    assert evaluate_power_risk(2200) == RiskLevel.NORMAL  # 경계: warning_max 이하
    assert evaluate_power_risk(2500) == RiskLevel.WARNING
    assert evaluate_power_risk(2860) == RiskLevel.WARNING  # 경계: danger_max 이하
    assert evaluate_power_risk(2861) == RiskLevel.DANGER
    assert evaluate_power_risk(3000) == RiskLevel.DANGER
    assert evaluate_power_risk(None) == RiskLevel.NORMAL  # 결측값 → 정상 fallback


@pytest.mark.django_db
def test_power_threshold_api_response_shape(db):
    """전력 임계값 API 응답 형태(caution/danger/maxY/unit) 일치 확인."""
    # 프론트엔드가 기대하는 응답 형태(caution/danger/maxY/unit) 유지 확인.
    from apps.monitoring.views.power_data import PowerThresholdView

    view = PowerThresholdView.as_view()
    req = APIRequestFactory().get("/monitoring/api/power/thresholds/")
    resp = view(req)
    resp.render()

    assert resp.status_code == 200
    assert resp.data == {
        "caution": 2200.0,
        "danger": 2860.0,
        "maxY": 3500.0,
        "unit": "W",
    }


@pytest.mark.django_db
def test_admin_threshold_change_invalidates_cache(db):
    """임계값 수정 → 캐시 무효화로 다음 조회·위험도 판정에 새 값 반영 확인."""
    # 어드민이 임계값 수정 → signal이 캐시 무효화 → 다음 호출에 새 값 반영.
    # DummyCache 환경에서도 DB 직접 조회 흐름은 동일하게 동작.
    from apps.facilities.models import Threshold

    first = get_threshold("power_default", "power_w")
    assert first["warning_max"] == 2200

    threshold = Threshold.objects.get(
        group__code="power_default", measurement_item="power_w"
    )
    threshold.warning_max = 1500
    threshold.save()

    after = get_threshold("power_default", "power_w")
    assert after["warning_max"] == 1500
    assert evaluate_power_risk(1800) == RiskLevel.WARNING


@pytest.mark.django_db
def test_facility_specific_threshold_overrides_legal(db, facility):
    """공장별 임계값이 전사 gas_legal 기준보다 우선 적용됨 확인."""
    # 공장별 임계값이 전사 기본값(gas_legal)보다 우선 적용되는지 확인.
    # facility=None → gas_legal 기준, facility 지정 → facility_default 우선.
    from decimal import Decimal

    from apps.facilities.models import Threshold, ThresholdGroup
    from apps.facilities.services.threshold_service import evaluate_gas_risk

    facility_group = ThresholdGroup.objects.get(code="gas_facility_default")
    Threshold.objects.create(
        group=facility_group,
        facility=facility,
        measurement_item="co",
        warning_max=Decimal("10"),
        danger_max=Decimal("50"),
        unit="ppm",
    )

    assert (
        evaluate_gas_risk("co", 15, facility_id=None) == RiskLevel.NORMAL
    )  # gas_legal 기준 (warning_max=25)
    assert (
        evaluate_gas_risk("co", 15, facility_id=facility.id) == RiskLevel.WARNING
    )  # facility 기준 (warning_max=10)


@pytest.mark.django_db
def test_facility_without_specific_falls_back_to_legal(db, facility):
    """공장별 임계값 없을 때 gas_legal 기준으로 fallback 확인."""
    # 공장별 임계값 없을 때 gas_legal로 자동 fallback 확인.
    # h2s: gas_legal warning_max=10, danger_max=15.
    from apps.facilities.services.threshold_service import evaluate_gas_risk

    assert evaluate_gas_risk("h2s", 12, facility_id=facility.id) == RiskLevel.WARNING
    assert evaluate_gas_risk("h2s", 20, facility_id=facility.id) == RiskLevel.DANGER
