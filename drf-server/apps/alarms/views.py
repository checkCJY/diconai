from collections import defaultdict

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from .models import AlarmRecord
from apps.accounts.models import CustomUser

# danger > warning 우선순위 매핑
LEVEL_PRIORITY = {"danger": 2, "warning": 1}


class MyStatusView(APIView):
    """
    GET /api/alarms/my-status/
    작업자 본인의 현재 활성 알람 중 최고 위험도를 반환.
    (is_active, alarm_level) 복합 인덱스를 활용.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        active_levels = list(
            AlarmRecord.objects.filter(
                worker=request.user,
                is_active=True,
            ).values_list("alarm_level", flat=True)
        )

        if not active_levels:
            status = "normal"
            active_alarm_level = None
        elif "danger" in active_levels:
            status = "danger"
            active_alarm_level = "danger"
        else:
            status = "warning"
            active_alarm_level = "warning"

        return Response(
            {
                "status": "success",
                "code": 200,
                "data": {
                    "worker_id": request.user.id,
                    "status": status,
                    "active_alarm_level": active_alarm_level,
                },
            }
        )


class WorkerSummaryView(APIView):
    """
    GET /api/alarms/worker-summary/
    관리자 소속 공장의 전체 작업자 위험도 집계.
    N+1 방지: worker_id__in 단일 쿼리 후 파이썬 레벨 집계.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type != "admin":
            raise PermissionDenied("접근 권한이 없습니다.")

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

        # 단일 쿼리로 활성 알람 조회 (N+1 방지)
        active_alarms = AlarmRecord.objects.filter(
            worker_id__in=worker_ids,
            is_active=True,
        ).values("worker_id", "alarm_level")

        # 파이썬 레벨에서 작업자별 최고 위험도 집계
        worker_max_level = defaultdict(lambda: None)
        for alarm in active_alarms:
            wid = alarm["worker_id"]
            lvl = alarm["alarm_level"]
            current = worker_max_level[wid]
            if current is None or LEVEL_PRIORITY[lvl] > LEVEL_PRIORITY.get(current, 0):
                worker_max_level[wid] = lvl

        danger_count = sum(1 for wid in worker_ids if worker_max_level[wid] == "danger")
        warning_count = sum(
            1 for wid in worker_ids if worker_max_level[wid] == "warning"
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
