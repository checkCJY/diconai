# alerts/models/event_acknowledgement.py
from django.conf import settings
from django.db import models

from apps.core.models.base import BaseModel


class EventAcknowledgement(BaseModel):
    """
    Event 의 사용자별(=user-scoped) 확인(ack) 상태 기록.

    [도입 배경 — 2026-05-15 알람 재설계]
    기존 Event.status = ACKNOWLEDGED 는 글로벌 단일 상태였음.
    즉 한 명의 운영자가 알람을 확인하면, 같은 Event 가 모든 사용자에게
    "이미 확인됨" 으로 표시되어 다른 사용자에게 더 이상 알람이 뜨지 않았음.

    팀 요구사항 — "본 사람만 안 보이고, 다른 사용자에게는 계속 뜸".
    이를 만족하기 위해 (event, user) 쌍별로 ack 기록을 별도 저장하는
    join 테이블을 신설. 기존 Event.status / acknowledged_by 는 손대지 않고
    공존시켜 글로벌 워크플로우(active → acknowledged → resolved) 의미는 유지.

    [재팝업 정책]
    위험 알람 재발생 시 fastapi broadcast 시점에 user 단위로 분기:
      if EventAcknowledgement.objects.filter(event=e, user=u).exists():
          → 이 user 에게는 push 생략
      else:
          → push (팝업 표시)
    Event 가 RESOLVED 되거나 새 Event 가 열리면 자연히 ack 가 무효화됨
    (FK CASCADE 로 자동 정리됨).

    [관계]
    - 한 Event 에 여러 user 의 ack 가 누적 (1:N).
    - UniqueConstraint(event, user) 로 중복 ack 차단.
    - ack 시각은 BaseModel.created_at 으로 조회 (별도 필드 미신설 — 의미 중복 회피).
    - Event/User 삭제 시 CASCADE — ack 기록은 단독 보존 의미 없음.

    [후속 의존성]
    - selectors.event_selector — user × event ack 조회 헬퍼 (다음 task)
    - services.event_service — broadcast 결정 시 이 모델 참조 (다음 task)
    - views.event — POST /alerts/api/events/{id}/ack/ 에서 get_or_create (다음 task)
    """

    event = models.ForeignKey(
        "alerts.Event",
        on_delete=models.CASCADE,
        related_name="acknowledgements",
        verbose_name="확인된 이벤트",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_acknowledgements",
        verbose_name="확인한 사용자",
    )

    class Meta:
        db_table = "event_acknowledgement"
        constraints = [
            # 같은 (event, user) 쌍에 ack 가 중복 생성되는 것을 DB 레벨에서 차단.
            # 애플리케이션 레이어에서 get_or_create 로도 보호하지만 race condition 대비.
            models.UniqueConstraint(
                fields=["event", "user"],
                name="uq_event_user_ack",
            ),
        ]
        indexes = [
            # 특정 user 의 ack 이력 최신순 조회 — broadcast 시점 분기 판단의 hot path.
            # event 에 user 가 ack 했는지 단일 조회는 unique constraint 가 자동으로 인덱싱하므로 별도 인덱스 불필요.
            models.Index(
                fields=["user", "-created_at"],
                name="idx_eventack_user_time",
            ),
        ]
