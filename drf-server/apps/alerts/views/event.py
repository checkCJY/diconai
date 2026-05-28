from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.alerts.models import Event, EventAcknowledgement, EventLog
from apps.alerts.serializers.event import EventListSerializer, EventDetailSerializer
from apps.core.constants import EventStatus
from apps.core.pagination import AdminPagination


@extend_schema_view(
    list=extend_schema(
        tags=["Events"],
        summary="이벤트 목록 조회 (읽기 전용)",
        description="`status` 쿼리로 pending/in_progress/resolved 필터링 가능.",
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                required=False,
                description="pending | in_progress | resolved",
            ),
        ],
    ),
    retrieve=extend_schema(
        tags=["Events"],
        summary="이벤트 상세 조회 (소속 알람 포함)",
    ),
)
class EventViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = Event.objects.select_related(
            "source_sensor",
            "source_power_device",
            "source_geofence",
            "worker",
            "policy",
        ).prefetch_related("alarms")

        # ?status=pending → active+acknowledged / in_progress / resolved
        status_param = self.request.query_params.get("status")
        if status_param == "pending":
            qs = qs.filter(status__in=[EventStatus.ACTIVE, EventStatus.ACKNOWLEDGED])
        elif status_param == "in_progress":
            qs = qs.filter(status=EventStatus.IN_PROGRESS)
        elif status_param == "resolved":
            qs = qs.filter(status=EventStatus.RESOLVED)

        return qs.order_by("-first_detected_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return EventDetailSerializer
        return EventListSerializer

    @extend_schema(
        tags=["Events"],
        summary="이벤트 상태 전환 (active → acknowledged → in_progress → resolved)",
        description=(
            "허용된 전환만 가능 — active→{ACK,IN_PROGRESS,RESOLVED}, ACK→{IN_PROGRESS,RESOLVED}, IN_PROGRESS→{RESOLVED}. "
            "전환 시 EventLog에 이력 기록 + acknowledged_by/resolved_by 자동 세팅."
        ),
        request=inline_serializer(
            name="EventStatusUpdateRequest",
            fields={
                "status": serializers.CharField(
                    help_text="acknowledged/in_progress/resolved"
                )
            },
        ),
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: EventDetailSerializer,
            400: OpenApiResponse(description="허용되지 않은 상태 전환"),
            404: OpenApiResponse(description="이벤트 없음"),
        },
    )
    @action(detail=True, methods=["patch"])
    def update_status(self, request, pk=None):
        event = self.get_object()
        new_status = request.data.get("status")

        allowed = {
            EventStatus.ACTIVE: [
                EventStatus.ACKNOWLEDGED,
                EventStatus.IN_PROGRESS,
                EventStatus.RESOLVED,
            ],
            EventStatus.ACKNOWLEDGED: [EventStatus.IN_PROGRESS, EventStatus.RESOLVED],
            EventStatus.IN_PROGRESS: [EventStatus.RESOLVED],
        }

        if new_status not in allowed.get(event.status, []):
            return Response(
                {
                    "error": f"현재 상태({event.status})에서 {new_status}로 변경할 수 없습니다."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous_status = event.status
        event.status = new_status
        if new_status == EventStatus.IN_PROGRESS and not event.acknowledged_by:
            event.acknowledged_by = request.user
            event.acknowledged_at = timezone.now()
        if new_status == EventStatus.RESOLVED:
            event.resolved_by = request.user
            event.resolved_at = timezone.now()
        event.save()

        action_map = {
            EventStatus.ACKNOWLEDGED: EventLog.Action.CONFIRMED,
            EventStatus.IN_PROGRESS: EventLog.Action.STATUS_CHANGED,
            EventStatus.RESOLVED: EventLog.Action.RESOLVED,
        }
        EventLog.objects.create(
            event=event,
            actor=request.user,
            action=action_map[new_status],
            previous_status=previous_status,
            new_status=new_status,
        )

        # 2026-05-15 알람 재설계: Event 가 RESOLVED 로 전이되면 떠있는 팝업을 닫게
        # 모든 WS 클라이언트에 broadcast. AlarmPayload.event_resolved_at 박힌 신호를
        # 받은 클라가 같은 event_id 팝업 close + "위험 해소" 토스트. WS 푸시 실패는
        # update_status 응답을 망치지 않도록 raise_on_failure=False — 트랜잭션은 성공.
        if new_status == EventStatus.RESOLVED:
            from apps.alerts.tasks import _push_to_ws

            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": event.event_type,
                    "risk_level": event.risk_level,
                    "source_label": event.source_label,
                    "summary": event.summary,
                    "message": f"위험 해소 — {event.source_label}",
                    "is_new_event": False,
                    "event_resolved_at": event.resolved_at.isoformat()
                    if event.resolved_at
                    else None,
                },
                raise_on_failure=False,
            )

        return Response(EventDetailSerializer(event).data)

    @extend_schema(
        tags=["Events"],
        summary="이벤트 사용자별 확인(ack) 기록 — user-scoped",
        description=(
            "프론트 알람 팝업의 '확인 완료' 클릭이 호출. (request.user, event) 쌍의 "
            "EventAcknowledgement 를 get_or_create — 이미 있으면 noop (idempotent). "
            "Event.status 는 건드리지 않음 (글로벌 워크플로우와 user-scoped 표시 관리 분리). "
            "재팝업 정책: 이 행이 있는 user 에게는 broadcast 시점에 push 생략."
        ),
        request=None,
        responses={
            200: inline_serializer(
                name="EventAcknowledgementResponse",
                fields={
                    "event_id": serializers.IntegerField(),
                    "user_id": serializers.IntegerField(),
                    "acknowledged_at": serializers.DateTimeField(),
                    "created": serializers.BooleanField(
                        help_text="True 면 신규 ack 생성, False 면 이미 ack 된 상태"
                    ),
                },
            ),
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            404: OpenApiResponse(description="이벤트 없음"),
        },
    )
    @action(detail=True, methods=["post"])
    def ack(self, request, pk=None):
        """
        Event 의 user-scoped 확인(ack) 기록.

        UniqueConstraint(event, user) 와 get_or_create 이중 보호로
        race condition 시에도 중복 row 가 생기지 않음. 응답의 `created` 필드로
        프론트가 "이미 ack 한 상태에서 다시 누른" 것을 구분 가능.
        """
        event = self.get_object()
        ack_obj, created = EventAcknowledgement.objects.get_or_create(
            event=event, user=request.user
        )
        return Response(
            {
                "event_id": event.id,
                "user_id": request.user.id,
                "acknowledged_at": ack_obj.created_at,
                "created": created,
            }
        )
