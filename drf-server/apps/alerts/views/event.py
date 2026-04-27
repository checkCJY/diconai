from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.alerts.models import Event
from apps.alerts.serializers.event import EventListSerializer, EventDetailSerializer
from apps.core.constants import EventStatus


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Event.objects.select_related(
            'source_sensor', 'source_power_device', 'source_geofence', 'worker'
        ).prefetch_related('alarms')

        # ?status=pending → active+acknowledged / in_progress / resolved
        status_param = self.request.query_params.get('status')
        if status_param == 'pending':
            qs = qs.filter(status__in=[EventStatus.ACTIVE, EventStatus.ACKNOWLEDGED])
        elif status_param == 'in_progress':
            qs = qs.filter(status=EventStatus.IN_PROGRESS)
        elif status_param == 'resolved':
            qs = qs.filter(status=EventStatus.RESOLVED)

        return qs.order_by('-first_detected_at')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return EventDetailSerializer
        return EventListSerializer

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        event = self.get_object()
        new_status = request.data.get('status')

        allowed = {
            EventStatus.ACTIVE:       [EventStatus.ACKNOWLEDGED, EventStatus.IN_PROGRESS, EventStatus.RESOLVED],
            EventStatus.ACKNOWLEDGED: [EventStatus.IN_PROGRESS, EventStatus.RESOLVED],
            EventStatus.IN_PROGRESS:  [EventStatus.RESOLVED],
        }

        if new_status not in allowed.get(event.status, []):
            return Response(
                {'error': f'현재 상태({event.status})에서 {new_status}로 변경할 수 없습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event.status = new_status
        if new_status == EventStatus.IN_PROGRESS and not event.acknowledged_by:
            event.acknowledged_by = request.user
            event.acknowledged_at = timezone.now()
        if new_status == EventStatus.RESOLVED:
            event.resolved_by  = request.user
            event.resolved_at  = timezone.now()
        event.save()

        return Response(EventDetailSerializer(event).data)
