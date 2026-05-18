# alerts/selectors/event_ack_selector.py
"""
EventAcknowledgement 읽기 전용 조회 헬퍼.

[도입 배경 — 2026-05-15 알람 재설계]
broadcast 시점에 "이 event 를 어떤 user 가 ack 했나" 를 빠르게 알아내야 함.
user 마다 SQL 1번씩 치는 N+1 패턴을 피하기 위해, 단일 쿼리로 set 을 반환하는
헬퍼를 제공.

이 모듈은 selectors 레이어 — 단순 읽기 조회만, 비즈니스 로직은 services 로.
"""

from apps.alerts.models import EventAcknowledgement


def get_acked_user_ids(event_id: int) -> set[int]:
    """
    특정 Event 를 ack 한 user_id 집합 반환.

    [사용 패턴 — broadcast 분기]
        acked = get_acked_user_ids(event.id)
        for candidate_id in candidate_user_ids:
            if candidate_id not in acked:
                push_to_user(candidate_id)

    [성능]
    EventAcknowledgement.event FK 인덱스 (UniqueConstraint(event,user) 가 자동 생성) 활용.
    한 Event 의 ack 행 개수가 보통 운영자 수(~수십명) 수준이라 set 메모리 부담 없음.

    Args:
        event_id: 조회 대상 Event 의 PK.

    Returns:
        ack 한 user_id 집합. 없으면 빈 set.
    """
    return set(
        EventAcknowledgement.objects.filter(event_id=event_id).values_list(
            "user_id", flat=True
        )
    )
