"""
전력 알람 흐름 회귀 테스트 (Phase 1~4 회귀 점검 Step 3).

[회귀 커버 대상]
- Phase 4-b power_alarm._evaluate(watt) DB Threshold 기반 위임
- Step 2 fix: alerts/tasks.py의 fire_power_*_task가 get_threshold(...) 사용
- Step 2 fix: PowerThresholdView API 응답이 DB 기반 (caution/danger/maxY/unit)
- threshold_service.evaluate_power_risk() warning/danger 경계 분기

[설계 결정]
통합 테스트 — DB Threshold 시드 의존, evaluate_power_risk() + PowerThresholdView 호출.
"""

import pytest
from django.core.cache import cache
from rest_framework.test import APIRequestFactory

from apps.core.constants import RiskLevel
from apps.facilities.services.threshold_service import (
    evaluate_power_risk,
    get_threshold,
    invalidate_threshold_cache,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """각 테스트 전후 Redis 캐시 비우기 (signal invalidate 부작용 회피)."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_get_threshold_returns_chart_max(db):
    """Step 2 fix: chart_max 백필 확인 (단일 진실 공급원)."""
    threshold = get_threshold("power_default", "power_w")
    assert threshold is not None
    assert threshold["warning_max"] == 2200
    assert threshold["danger_max"] == 2860
    assert threshold["chart_max"] == 3500
    assert threshold["unit"] == "W"


@pytest.mark.django_db
def test_evaluate_power_risk_normal_warning_danger(db):
    """Phase 4-b: DB 기반 위험도 분기 9개 케이스."""
    invalidate_threshold_cache("power_default", "power_w")
    assert evaluate_power_risk(1000) == RiskLevel.NORMAL
    assert evaluate_power_risk(2200) == RiskLevel.NORMAL  # 경계: warning_max 이하
    assert evaluate_power_risk(2500) == RiskLevel.WARNING  # 2200 < x <= 2860
    assert evaluate_power_risk(2860) == RiskLevel.WARNING  # 경계: danger_max 이하
    assert evaluate_power_risk(2861) == RiskLevel.DANGER
    assert evaluate_power_risk(3000) == RiskLevel.DANGER
    assert evaluate_power_risk(None) == RiskLevel.NORMAL  # 결측 fallback


@pytest.mark.django_db
def test_power_threshold_api_response_shape(db):
    """Step 2 fix: PowerThresholdView 응답이 기존 dict 구조 호환 (caution/danger/maxY/unit)."""
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
    """어드민이 Threshold 수정 → signal invalidate → 다음 호출에 새 값 반영."""
    from apps.facilities.models import Threshold

    # 첫 호출로 캐시 채움
    first = get_threshold("power_default", "power_w")
    assert first["warning_max"] == 2200

    # 어드민이 운영 정책 변경 (warning_max 1500으로 강화)
    threshold = Threshold.objects.get(
        group__code="power_default", measurement_item="power_w"
    )
    threshold.warning_max = 1500
    threshold.save()  # signal이 cache invalidate

    # 다음 호출은 새 값 반영
    after = get_threshold("power_default", "power_w")
    assert after["warning_max"] == 1500
    # 위험도 판정도 즉시 반영
    assert evaluate_power_risk(1800) == RiskLevel.WARNING
