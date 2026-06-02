"""알람 수신 대상자 조회 — 읽기 전용 selector.

"이 알람을 누구에게 보낼 것인가"의 단일 출처. 인앱 WS·Discord 등 발송 채널이
공통으로 이 결과(worker_id 목록)를 받아 분배한다.

발송 위치(FastAPI)는 Django ORM이 없어 CustomUser를 직접 조회할 수 없으므로,
대상 계산은 DRF 측에서만 수행하고 id 목록만 payload로 전달한다.
"""

from django.contrib.auth import get_user_model

from apps.core.constants import UserType

User = get_user_model()


def get_facility_worker_ids(facility_id: int) -> list[int]:
    """해당 시설의 활성 작업자(user_type=worker) id 목록.

    가스/전력 DANGER 대피 알림 수신 대상. 가스는 구역 무관 확산하므로 시설 전원에
    통보한다. idx_user_facility_type_active 인덱스로 조회.

    수신 범위를 "현재 위험 구역 안에 있는 작업자"로 좁히려면(위치 기반) 본 셀렉터만
    WorkerPosition 기준 쿼리로 교체하면 된다 — 발송 분배 코드는 그대로.

    Args:
        facility_id: 알람이 발생한 시설 id.

    Returns:
        작업자 id 목록. 대상 없으면 빈 list.
    """
    if not facility_id:
        return []
    return list(
        User.objects.filter(
            facility_id=facility_id,
            user_type=UserType.WORKER,
            is_active=True,
        ).values_list("id", flat=True)
    )
