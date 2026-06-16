# 이성현 수정 — TestCase → pytest 방식으로 전환 (PostgreSQL 호환)
# setUpTestData + delete() 조합이 PG 트랜잭션과 충돌하는 문제 해결.
# 각 테스트 함수가 독립적으로 AlertPolicy를 생성/정리하도록 변경.
import pytest

from apps.alerts.models import AlertPolicy
from apps.alerts.services.policy_matcher import (
    compute_condition_summary,
    match_policy,
    save_policy,
)
from apps.core.constants import AlarmType
from apps.facilities.models import Facility


@pytest.fixture
def facility_a(db):
    return Facility.objects.create(name="공장 A")


@pytest.fixture
def facility_b(db):
    return Facility.objects.create(name="공장 B")


@pytest.fixture(autouse=True)
def clear_policies(db):
    """각 테스트 전 마이그레이션 시드 정책 제거 — 본 파일은 정책을 직접 만들어 검증."""
    AlertPolicy.objects.all().delete()


@pytest.mark.django_db
def test_match_specific_facility(facility_a):
    """target_facility 일치 정책 매칭."""
    policy = AlertPolicy.objects.create(
        name="A 가스",
        event_type=AlarmType.GAS_THRESHOLD,
        target_facility=facility_a,
        target_user_types=["facility_admin"],
        channels=["popup"],
    )
    match = match_policy(event_type=AlarmType.GAS_THRESHOLD, facility_id=facility_a.id)
    assert match == policy


@pytest.mark.django_db
def test_match_global_policy_when_facility_specific_absent(facility_a):
    """전사 정책 (target_facility=NULL) fallback."""
    global_policy = AlertPolicy.objects.create(
        name="전사 가스",
        event_type=AlarmType.GAS_THRESHOLD,
        target_facility=None,
        target_user_types=["super_admin"],
        channels=["popup"],
    )
    match = match_policy(event_type=AlarmType.GAS_THRESHOLD, facility_id=facility_a.id)
    assert match == global_policy


@pytest.mark.django_db
def test_match_specific_takes_priority_over_global(facility_a):
    """특정 facility 정책이 전사 정책보다 우선."""
    AlertPolicy.objects.create(
        name="전사",
        event_type=AlarmType.GAS_THRESHOLD,
        target_facility=None,
        target_user_types=["super_admin"],
        channels=["popup"],
    )
    specific = AlertPolicy.objects.create(
        name="A 공장 전용",
        event_type=AlarmType.GAS_THRESHOLD,
        target_facility=facility_a,
        target_user_types=["facility_admin"],
        channels=["popup"],
    )
    match = match_policy(event_type=AlarmType.GAS_THRESHOLD, facility_id=facility_a.id)
    assert match == specific


@pytest.mark.django_db
def test_no_match_returns_none(facility_a, facility_b):
    """일치하는 정책 없음 → None."""
    AlertPolicy.objects.create(
        name="B 가스",
        event_type=AlarmType.GAS_THRESHOLD,
        target_facility=facility_b,
        target_user_types=["facility_admin"],
        channels=["popup"],
    )
    match = match_policy(event_type=AlarmType.GAS_THRESHOLD, facility_id=facility_a.id)
    assert match is None


@pytest.mark.django_db
def test_save_policy_updates_condition_summary(facility_a):
    """save_policy() 호출 시 condition_summary 자동 갱신."""
    policy = AlertPolicy(
        name="테스트",
        event_type=AlarmType.PPE_VIOLATION,
        target_facility=facility_a,
        target_user_types=["worker"],
        channels=["popup", "sms"],
    )
    save_policy(policy)
    assert "PPE 미착용" in policy.condition_summary
    assert "공장 A" in policy.condition_summary
    # 채널은 사람이 읽는 한글 라벨로 렌더된다 (popup→"관제 실시간 알림", sms→"SMS").
    # 원시 코드("popup, sms")가 아니라 라벨 노출이 condition_summary 의 계약.
    assert "관제 실시간 알림" in policy.condition_summary
    assert "SMS" in policy.condition_summary


@pytest.mark.django_db
def test_compute_condition_summary_global():
    """전사 정책 condition_summary는 '전사' 포함."""
    policy = AlertPolicy(
        name="전사 PPE",
        event_type=AlarmType.PPE_VIOLATION,
        target_facility=None,
        target_user_types=["worker"],
        channels=["popup"],
    )
    summary = compute_condition_summary(policy)
    assert "전사" in summary
