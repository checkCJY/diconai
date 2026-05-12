# facilities/selectors/facility.py
"""
Facility 마스터 조회 헬퍼.

[기본 공장 폴백]
단일 공장 운영 단계에서 user.facility_id가 NULL인 super_admin / facility_admin이
어드민·운영자 페이지에 진입했을 때, 첫 활성 facility를 자동으로 사용해 UX를 단순화한다.
공장이 여러 개인 환경으로 전환되면 호출부에서 명시적으로 facility_id를 지정해야 한다.
"""

from apps.facilities.models.facility import Facility


def get_default_facility_id() -> int | None:
    """첫 활성 facility id. 활성 facility가 없으면 None."""
    return (
        Facility.objects.filter(is_active=True)
        .order_by("id")
        .values_list("id", flat=True)
        .first()
    )
