from collections import defaultdict
from datetime import datetime, timedelta, timezone as py_timezone

from django.db.models import Count, Q
from django.utils import timezone

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import CustomUser
from apps.alerts.models import AlarmRecord, Event
from apps.alerts.serializers import (
    AlarmRecordSerializer,
    MyStatusResponseSerializer,
    WorkerSummaryResponseSerializer,
)
from apps.core.constants import EventStatus, RiskLevel
from apps.core.permissions import IsSuperAdminOrFacilityAdmin

LEVEL_PRIORITY = {RiskLevel.DANGER: 2, RiskLevel.WARNING: 1}


class MyStatusView(APIView):
    """
    GET /api/alerts/my-status/
    작업자 본인의 미해결 이벤트 중 최고 위험도를 반환.
    구버전의 AlarmRecord.is_active → Event.status != resolved 로 대체.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Alerts"],
        summary="작업자 본인의 미해결 이벤트 위험도 (최댓값)",
        description="active 상태(EventStatus.RESOLVED 아닌) 이벤트 중 가장 높은 risk_level을 status로 반환.",
        responses={
            200: MyStatusResponseSerializer,
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
        },
        examples=[
            OpenApiExample(
                "정상 (미해결 이벤트 없음)",
                value={
                    "status": "success",
                    "code": 200,
                    "data": {
                        "worker_id": 5,
                        "status": "normal",
                        "active_risk_level": None,
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "위험 이벤트 진행 중",
                value={
                    "status": "success",
                    "code": 200,
                    "data": {
                        "worker_id": 5,
                        "status": "danger",
                        "active_risk_level": "danger",
                    },
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        active_levels = list(
            Event.objects.filter(
                worker=request.user,
            )
            .exclude(status=EventStatus.RESOLVED)
            .values_list("risk_level", flat=True)
        )

        if not active_levels:
            status = "normal"
            active_risk_level = None
        elif RiskLevel.DANGER in active_levels:
            status = RiskLevel.DANGER
            active_risk_level = RiskLevel.DANGER
        else:
            status = RiskLevel.WARNING
            active_risk_level = RiskLevel.WARNING

        return Response(
            {
                "status": "success",
                "code": 200,
                "data": {
                    "worker_id": request.user.id,
                    "status": status,
                    "active_risk_level": active_risk_level,
                },
            }
        )


class WorkerSummaryView(APIView):
    """
    GET /api/alerts/worker-summary/
    관리자 소속 공장의 전체 작업자 위험도 집계.
    구버전의 AlarmRecord.is_active → Event.status != resolved 로 대체.
    """

    permission_classes = [IsAuthenticated, IsSuperAdminOrFacilityAdmin]

    @extend_schema(
        tags=["Alerts"],
        summary="공장 내 작업자 위험도 집계 (관리자 전용)",
        description="자기 공장 작업자들의 미해결 이벤트를 집계해 위험도별 인원수 반환.",
        responses={
            200: WorkerSummaryResponseSerializer,
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            403: OpenApiResponse(description="관리자 권한 필요"),
        },
        examples=[
            OpenApiExample(
                "정상 응답 — 25명 중 위험 1, 주의 4",
                value={
                    "status": "success",
                    "code": 200,
                    "data": {
                        "facility_id": 1,
                        "total_count": 25,
                        "normal_count": 20,
                        "warning_count": 4,
                        "danger_count": 1,
                    },
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request):
        # 권한 체크는 permission_classes(IsSuperAdminOrFacilityAdmin)가 처리
        facility = request.user.facility
        if facility is None:
            return Response(
                {
                    "status": "success",
                    "code": 200,
                    "data": {
                        "facility_id": None,
                        "total_count": 0,
                        "normal_count": 0,
                        "warning_count": 0,
                        "danger_count": 0,
                    },
                }
            )

        facility_id = facility.id
        worker_ids = list(
            CustomUser.objects.filter(
                facility_id=facility_id,
                user_type="worker",
            ).values_list("id", flat=True)
        )
        total_count = len(worker_ids)

        if total_count == 0:
            return Response(
                {
                    "status": "success",
                    "code": 200,
                    "data": {
                        "facility_id": facility_id,
                        "total_count": 0,
                        "normal_count": 0,
                        "warning_count": 0,
                        "danger_count": 0,
                    },
                }
            )

        active_events = (
            Event.objects.filter(worker_id__in=worker_ids)
            .exclude(status=EventStatus.RESOLVED)
            .values("worker_id", "risk_level")
        )

        worker_max_level = defaultdict(lambda: None)
        for event in active_events:
            wid = event["worker_id"]
            lvl = event["risk_level"]
            current = worker_max_level[wid]
            if current is None or LEVEL_PRIORITY.get(lvl, 0) > LEVEL_PRIORITY.get(
                current, 0
            ):
                worker_max_level[wid] = lvl

        danger_count = sum(
            1 for wid in worker_ids if worker_max_level[wid] == RiskLevel.DANGER
        )
        warning_count = sum(
            1 for wid in worker_ids if worker_max_level[wid] == RiskLevel.WARNING
        )
        normal_count = total_count - danger_count - warning_count

        return Response(
            {
                "status": "success",
                "code": 200,
                "data": {
                    "facility_id": facility_id,
                    "total_count": total_count,
                    "normal_count": normal_count,
                    "warning_count": warning_count,
                    "danger_count": danger_count,
                },
            }
        )


@extend_schema_view(
    list=extend_schema(
        tags=["Alerts"],
        summary="알람 기록 목록 (읽기 전용)",
        parameters=[
            OpenApiParameter(
                name="ordering",
                type=str,
                required=False,
                description="-created_at | risk_level",
            ),
        ],
    ),
    retrieve=extend_schema(tags=["Alerts"], summary="알람 기록 상세"),
)
class AlarmRecordViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AlarmRecordSerializer
    queryset = AlarmRecord.objects.all()

    def get_queryset(self):
        queryset = AlarmRecord.objects.select_related(
            "sensor", "power_device", "worker", "geofence", "event"
        )

        ordering = self.request.query_params.get("ordering", "-created_at")
        if ordering == "risk_level":
            queryset = queryset.order_by("-risk_level", "-created_at")
        else:
            queryset = queryset.order_by("-created_at")

        return queryset

    @extend_schema(
        tags=["Alerts"],
        summary="최근 24시간 알람 요약 + 현재 미확인 이벤트 건수",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="AlarmSummaryResponse",
                fields={
                    "last_24h_total": serializers.IntegerField(),
                    "last_24h_danger": serializers.IntegerField(),
                    "last_24h_warning": serializers.IntegerField(),
                    "unacknowledged_event_count": serializers.IntegerField(),
                    "user_unread_event_count": serializers.IntegerField(),
                },
            ),
        },
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """최근 24시간 AlarmRecord 누적 + 현재 미확인 Event 건수.

        24h 누적 (last_24h_*) 은 운영 통계용, 미확인 (unacknowledged_event_count) 은
        "지금 운영자가 처리해야 할 사건 수". Event.status ∈ {active, acknowledged,
        in_progress} 가 미확인 (resolved 는 처리 완료라 제외).

        user_unread_event_count — 본인이 아직 ack 안 한 활성 이벤트 수
        (EventAcknowledgement 활용). 헤더 미확인 배지의 초기값. 글로벌 unacknowledged
        와 달리 본 사람만 줄어드는 카운트.
        """
        from apps.alerts.models import Event
        from apps.alerts.selectors.event_ack_selector import (
            get_user_unread_event_count,
        )
        from apps.core.constants import EventStatus

        last_24h = timezone.now() - timedelta(hours=24)
        qs = AlarmRecord.objects.filter(created_at__gte=last_24h)

        data = qs.aggregate(
            total=Count("id"),
            danger=Count("id", filter=Q(risk_level=RiskLevel.DANGER)),
            warning=Count("id", filter=Q(risk_level=RiskLevel.WARNING)),
        )

        unack_count = Event.objects.filter(
            status__in=[
                EventStatus.ACTIVE,
                EventStatus.ACKNOWLEDGED,
                EventStatus.IN_PROGRESS,
            ],
        ).count()

        user_unread = get_user_unread_event_count(request.user.id)

        return Response(
            {
                "last_24h_total": data["total"],
                "last_24h_danger": data["danger"],
                "last_24h_warning": data["warning"],
                "unacknowledged_event_count": unack_count,
                "user_unread_event_count": user_unread,
            }
        )

    @extend_schema(
        tags=["Alerts"],
        summary="WS 재연결 catch-up — since 이후 24h 내 미수신 알람",
        description=(
            "클라이언트가 WS 끊김 후 재연결할 때 localStorage 의 last_seen_ts 를 "
            "since 로 전달해 미수신 알람을 보충. "
            "fastapi 거치지 않고 클라가 drf 직접 호출 — simplicity. "
            "응답 모양은 fastapi broadcast payload 와 동일해 클라 측 mapper 공용 처리 가능. "
            "since=24h 이상 과거면 24h 까지로 클램프. 최대 100건 응답."
        ),
        parameters=[
            OpenApiParameter(
                name="since",
                type=float,
                required=True,
                description="unix timestamp (초 단위). 누락/잘못된 값이면 빈 list 반환.",
            ),
        ],
        responses={
            200: inline_serializer(
                name="AlarmCatchUpResponse",
                fields={
                    "alarms": serializers.ListField(child=serializers.DictField()),
                },
            ),
            401: OpenApiResponse(description="인증 필요"),
        },
    )
    @action(detail=False, methods=["get"], url_path="catch-up")
    def catch_up(self, request):
        """since 이후 24h 내 AlarmRecord 를 broadcast payload 모양으로 반환.

        [상한] 24h 클램프 + 최대 100건 — race 패킷 폭주 방지.
        [응답 키] fastapi alarm_router 의 AlarmPayload 와 동일 필드명. 누락 시 빈 list.
        """
        since_str = request.query_params.get("since")
        if not since_str:
            return Response({"alarms": []})
        try:
            since_dt = datetime.fromtimestamp(float(since_str), tz=py_timezone.utc)
        except (ValueError, TypeError):
            return Response({"alarms": []})

        floor = timezone.now() - timedelta(hours=24)
        if since_dt < floor:
            since_dt = floor

        alarms = (
            AlarmRecord.objects.filter(created_at__gte=since_dt)
            # power_device prefetch — get_short_message 가 channel_meta 조회 시 N+1 회피.
            .select_related("event", "power_device")
            .order_by("created_at")[:100]
        )

        return Response(
            {
                "alarms": [
                    {
                        "event_id": a.event_id,
                        "alarm_type": a.alarm_type,
                        "risk_level": a.risk_level,
                        "source_label": a.event.source_label if a.event_id else "",
                        "summary": a.event.summary if a.event_id else "",
                        "message": a.get_short_message(),
                        "is_new_event": False,
                        "created_at": a.created_at.isoformat(),
                    }
                    for a in alarms
                ]
            }
        )
