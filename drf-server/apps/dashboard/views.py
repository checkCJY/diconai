import calendar
from datetime import date

from django.conf import settings
from django.db.models import Exists, OuterRef
from django.shortcuts import render
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .menu import get_menu_tree

ADMIN_TYPES = ("super_admin", "facility_admin")


# ──────────────────────────────────────────────────────────
# HTML 페이지 뷰
# ──────────────────────────────────────────────────────────
def main_dashboard(request):
    return render(request, "dashboard/main.html")


def my_profile_page(request):
    return render(request, "snb_details/my_profile.html")


def safety_checklist_page(request):
    return render(request, "snb_details/safety_checklist.html")


def safety_history_page(request):
    return render(request, "snb_details/safety_history.html")


def safety_vr_page(request):
    return render(request, "snb_details/safety_vr.html")


def monitoring_realtime_page(request):
    return render(request, "snb_details/monitoring_realtime.html")


def monitoring_gas_page(request):
    return render(request, "snb_details/monitoring_gas.html")


def monitoring_power_page(request):
    return render(request, "snb_details/monitoring_power.html")


def monitoring_workers_page(request):
    return render(request, "snb_details/monitoring_workers.html")


def monitoring_events_page(request):
    return render(request, "snb_details/monitoring_events.html")


def monitoring_event_detail_page(request, event_id):
    return render(request, "snb_details/event_detail.html", {"event_id": event_id})


# ──────────────────────────────────────────────────────────
# GET /api/menu/
# ──────────────────────────────────────────────────────────
class MenuView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Dashboard"],
        summary="사용자 권한 기반 메뉴 트리 조회",
        description="user_type(worker/facility_admin/super_admin/viewer)에 따라 다른 메뉴 트리를 반환.",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="MenuResponse",
                fields={"menu": serializers.ListField(child=serializers.DictField())},
            ),
            500: OpenApiResponse(description="메뉴 조회 실패"),
        },
    )
    def get(self, request):
        try:
            menu = get_menu_tree(request.user.user_type)
        except Exception:
            return Response(
                {"error": "메뉴를 불러올 수 없습니다."},
                status=500,
            )
        return Response({"menu": menu})


# ──────────────────────────────────────────────────────────
# GET /api/dashboard/refresh/
# ──────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────
# GET/POST /api/vr-progress/ — VR 시청 위치 임시 저장 (세션)
# ──────────────────────────────────────────────────────────
class VRProgressView(APIView):
    permission_classes = [AllowAny]

    SESSION_KEY = "vr_safety_progress"

    @extend_schema(
        tags=["Dashboard"],
        summary="VR 안전교육 시청 위치 조회 (세션)",
        responses={
            200: inline_serializer(
                name="VRProgressGet",
                fields={"position": serializers.FloatField()},
            )
        },
    )
    def get(self, request):
        position = request.session.get(self.SESSION_KEY, 0)
        return Response({"position": position})

    @extend_schema(
        tags=["Dashboard"],
        summary="VR 안전교육 시청 위치 저장 (세션)",
        request=inline_serializer(
            name="VRProgressPost",
            fields={"position": serializers.FloatField()},
        ),
        responses={
            200: inline_serializer(
                name="VRProgressSaved",
                fields={"saved": serializers.FloatField()},
            )
        },
    )
    def post(self, request):
        try:
            position = float(request.data.get("position", 0))
        except (TypeError, ValueError):
            position = 0
        request.session[self.SESSION_KEY] = position
        return Response({"saved": position})


# ──────────────────────────────────────────────────────────
# GET/POST /api/safety-status/ — 나의 안전확인 완료 상태 (세션 기반)
# ──────────────────────────────────────────────────────────
class MySafetyStatusView(APIView):
    permission_classes = [AllowAny]

    CHECKLIST_KEY = "safety_checklist_done_date"
    VR_KEY = "safety_vr_done_date"

    def _is_done_today(self, request, key):
        stored = request.session.get(key)
        return stored == str(date.today())

    @extend_schema(
        tags=["Dashboard"],
        summary="오늘의 안전확인 완료 상태 조회 (세션)",
        description="체크리스트와 VR 교육 완료 여부. Django 세션 기반으로 일자별 초기화.",
        responses={
            200: inline_serializer(
                name="SafetyStatusResponse",
                fields={
                    "checklist_done": serializers.BooleanField(),
                    "vr_done": serializers.BooleanField(),
                },
            )
        },
    )
    def get(self, request):
        return Response(
            {
                "checklist_done": self._is_done_today(request, self.CHECKLIST_KEY),
                "vr_done": self._is_done_today(request, self.VR_KEY),
            }
        )

    @extend_schema(
        tags=["Dashboard"],
        summary="안전확인 완료 표시",
        description="`key='checklist'` 또는 `key='vr'`로 호출해 오늘 날짜를 세션에 저장.",
        request=inline_serializer(
            name="SafetyStatusUpdate",
            fields={"key": serializers.ChoiceField(choices=["checklist", "vr"])},
        ),
        responses={
            200: inline_serializer(
                name="OkResponse2", fields={"ok": serializers.BooleanField()}
            ),
            400: OpenApiResponse(description="허용되지 않은 key값"),
        },
    )
    def post(self, request):
        key_name = request.data.get("key")
        if key_name == "checklist":
            request.session[self.CHECKLIST_KEY] = str(date.today())
        elif key_name == "vr":
            request.session[self.VR_KEY] = str(date.today())
        else:
            return Response(
                {"error": "key는 'checklist' 또는 'vr'이어야 합니다."}, status=400
            )
        return Response({"ok": True})


# ──────────────────────────────────────────────────────────
# GET /api/safety-history/?month=YYYY-MM[&worker_id=X]
# ──────────────────────────────────────────────────────────
class SafetyHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Dashboard"],
        summary="월별 안전확인 이력 조회",
        description="관리자는 `worker_id` 파라미터로 다른 작업자 이력 조회 가능. 월의 매일 항목을 모두 반환.",
        parameters=[
            OpenApiParameter(
                name="month", type=str, required=False, description="YYYY-MM"
            ),
            OpenApiParameter(
                name="worker_id",
                type=int,
                required=False,
                description="관리자만 다른 사용자 조회 가능",
            ),
        ],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="SafetyHistoryResponse",
                fields={
                    "month": serializers.CharField(),
                    "joined_date": serializers.CharField(),
                    "worker_name": serializers.CharField(),
                    "records": serializers.ListField(
                        child=inline_serializer(
                            name="SafetyHistoryRecord",
                            fields={
                                "date": serializers.CharField(),
                                "checklist_done": serializers.BooleanField(),
                                "vr_done": serializers.BooleanField(),
                            },
                        )
                    ),
                },
            ),
            404: OpenApiResponse(description="작업자 없음"),
        },
    )
    def get(self, request):
        month_str = request.query_params.get("month", "")
        try:
            year, month = int(month_str[:4]), int(month_str[5:7])
        except (ValueError, IndexError):
            today = date.today()
            year, month = today.year, today.month

        # 관리자는 worker_id 파라미터로 다른 작업자 이력 조회 가능
        worker_id = request.query_params.get("worker_id")
        if worker_id and request.user.user_type in ADMIN_TYPES:
            from apps.accounts.models import CustomUser

            try:
                target = CustomUser.objects.get(pk=worker_id)
            except CustomUser.DoesNotExist:
                return Response({"error": "작업자를 찾을 수 없습니다."}, status=404)
        else:
            target = request.user

        from apps.safety.models.safety import SafetyStatus

        checked_dates = set(
            SafetyStatus.objects.filter(
                worker=target,
                is_checked=True,
                checked_at__year=year,
                checked_at__month=month,
            ).values_list("checked_at__date", flat=True)
        )

        _, days_in_month = calendar.monthrange(year, month)
        records = []
        for day in range(1, days_in_month + 1):
            d = date(year, month, day)
            records.append(
                {
                    "date": d.isoformat(),
                    "checklist_done": d in checked_dates,
                    "vr_done": False,  # 4차 연동 예정
                }
            )

        return Response(
            {
                "month": f"{year:04d}-{month:02d}",
                "joined_date": target.date_joined.date().isoformat(),
                "worker_name": target.name or target.username,
                "records": records,
            }
        )


# ──────────────────────────────────────────────────────────
# GET /api/workers-list/?department_id=X&name=Y
# ──────────────────────────────────────────────────────────
class WorkerListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Dashboard"],
        summary="작업자 목록 + 부서 드롭다운 (관리자 전용)",
        description=(
            "facility_admin은 자기 공장 작업자만, super_admin은 전체. "
            "오늘 위치 데이터 유무로 `is_present` 자동 계산."
        ),
        parameters=[
            OpenApiParameter(name="department_id", type=int, required=False),
            OpenApiParameter(
                name="name", type=str, required=False, description="이름 부분검색"
            ),
        ],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="WorkerListResponse",
                fields={
                    "workers": serializers.ListField(
                        child=inline_serializer(
                            name="WorkerItem",
                            fields={
                                "id": serializers.IntegerField(),
                                "name": serializers.CharField(),
                                "department": serializers.CharField(),
                                "department_id": serializers.IntegerField(
                                    allow_null=True
                                ),
                                "is_present": serializers.BooleanField(),
                            },
                        )
                    ),
                    "departments": serializers.ListField(
                        child=inline_serializer(
                            name="DeptItem",
                            fields={
                                "id": serializers.IntegerField(),
                                "name": serializers.CharField(),
                            },
                        )
                    ),
                },
            ),
            403: OpenApiResponse(description="관리자 권한 필요"),
        },
    )
    def get(self, request):
        if request.user.user_type not in ADMIN_TYPES:
            return Response({"error": "권한이 없습니다."}, status=403)

        from apps.accounts.models import CustomUser, Department
        from apps.positioning.models.worker_position import WorkerPosition

        workers = CustomUser.objects.filter(
            user_type="worker",
            deactivated_at__isnull=True,
        )

        if request.user.user_type == "facility_admin":
            workers = workers.filter(facility=request.user.facility)

        dept_id = request.query_params.get("department_id")
        if dept_id:
            workers = workers.filter(
                dept_memberships__department_id=dept_id,
                dept_memberships__is_primary=True,
            )

        name_q = request.query_params.get("name", "").strip()
        if name_q:
            workers = workers.filter(name__icontains=name_q)

        today = date.today()
        today_positions = WorkerPosition.objects.filter(
            worker=OuterRef("pk"),
            measured_at__date=today,
        )
        workers = (
            workers.annotate(is_present=Exists(today_positions))
            .prefetch_related("dept_memberships__department")
            .order_by("name")
        )

        worker_list = [
            {
                "id": w.id,
                "name": w.name or w.username,
                "department": w.department.name if w.department else "-",
                "department_id": w.department_id,
                "is_present": w.is_present,
            }
            for w in workers
        ]

        # 부서 드롭다운용
        if request.user.user_type == "facility_admin":
            depts = (
                Department.objects.filter(
                    memberships__user__facility=request.user.facility,
                    memberships__user__user_type="worker",
                    is_active=True,
                )
                .distinct()
                .order_by("code")
            )
        else:
            depts = Department.objects.filter(is_active=True).order_by("code")

        dept_list = [{"id": d.id, "name": d.name} for d in depts]

        return Response({"workers": worker_list, "departments": dept_list})


class DashboardRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Dashboard"],
        summary="대쉬보드 새로고침 (권한 의존 admin_url 갱신)",
        description=(
            "헤더 새로고침 버튼 클릭 시 호출. 관리자 권한이면 `admin_url`을 응답에 포함해 "
            "어드민 메뉴 버튼을 노출하는 트리거. 일반 사용자는 빈 dict."
        ),
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="DashboardRefreshResponse",
                fields={"admin_url": serializers.CharField(required=False)},
            ),
        },
    )
    def get(self, request):
        data = {}
        if request.user.user_type in ("facility_admin", "super_admin"):
            data["admin_url"] = getattr(
                settings, "ADMIN_BACKOFFICE_URL", "/admin-panel/accounts-management/"
            )
        return Response(data)
