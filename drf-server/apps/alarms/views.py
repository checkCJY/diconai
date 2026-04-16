# Create your views here.
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q

from .models import AlarmRecord
from .serializers import AlarmRecordSerializer


class AlarmRecordViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AlarmRecordSerializer
    queryset = AlarmRecord.objects.all()

    def get_queryset(self):
        queryset = AlarmRecord.objects.select_related(
            'sensor', 'worker', 'geofence'
        )
        # 정렬 (기본: 최신순 / 위험도순 선택 가능)
        ordering = self.request.query_params.get('ordering', '-created_at')
        if ordering == 'alarm_level':
            queryset = queryset.order_by('-alarm_level', '-created_at')
        else:
            queryset = queryset.order_by('-created_at')

        # 진행 중인 알람만 필터
        is_active = self.request.query_params.get('is_active')
        if is_active == 'true':
            queryset = queryset.filter(is_active=True)

        return queryset

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """최근 24시간 이벤트 요약"""
        last_24h = timezone.now() - timedelta(hours=24)
        qs = AlarmRecord.objects.filter(created_at__gte=last_24h)

        data = qs.aggregate(
            total=Count('id'),
            danger=Count('id', filter=Q(alarm_level='danger')),
            warning=Count('id', filter=Q(alarm_level='warning')),
        )
        return Response({
            'last_24h_total': data['total'],
            'last_24h_danger': data['danger'],
            'last_24h_warning': data['warning'],
        })