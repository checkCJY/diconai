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


def get_user_unread_event_count(user_id: int) -> int:
    """
    특정 user 가 ack 안 한 active/acknowledged/in_progress Event 개수 반환.

    [도입 배경 — 2026-05-17 D 옵션 헤더 미확인 배지]
    헤더의 "🔔 N" 배지 초기값 — 본인이 아직 확인 완료 안 한 활성 이벤트 수.
    글로벌 unacknowledged_event_count (Event.status 기반) 와 달리, user-scoped
    ack (Phase 1 EventAcknowledgement) 을 기준으로 본 사람만 카운트 ↓.

    [성능]
    NOT EXISTS subquery — EventAcknowledgement.UniqueConstraint(event, user) 인덱스
    가 자동 활용. count() 단일 SQL.

    Args:
        user_id: 조회 대상 user 의 PK.

    Returns:
        ack 안 한 활성 이벤트 개수. 운영자가 처리해야 할 사건 수.
    """
    from apps.alerts.models import Event
    from apps.core.constants import EventStatus

    return (
        Event.objects.filter(
            status__in=[
                EventStatus.ACTIVE,
                EventStatus.ACKNOWLEDGED,
                EventStatus.IN_PROGRESS,
            ],
        )
        .exclude(acknowledgements__user_id=user_id)
        .count()
    )
