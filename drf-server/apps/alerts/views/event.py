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

from apps.alerts.models import Event, EventLog
from apps.alerts.serializers.event import EventListSerializer, EventDetailSerializer
from apps.core.constants import EventStatus


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

    def get_queryset(self):
        qs = Event.objects.select_related(
            "source_sensor", "source_power_device", "source_geofence", "worker"
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

        return Response(EventDetailSerializer(event).data)
