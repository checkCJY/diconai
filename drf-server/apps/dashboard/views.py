import calendar
import logging
from datetime import date

from django.conf import settings
from django.db.models import Exists, OuterRef
from django.shortcuts import render
from django.utils import timezone
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

from apps.facilities.selectors.facility import get_default_facility_id
from apps.training.services.vr_admin_service import get_vr_content_for_facility

from .menu import get_menu_tree

logger = logging.getLogger(__name__)

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
    """작업자 VR 교육 페이지 (HTML 셸).

    [동적 영상 연동]
    작업자 본인 facility의 활성 `VRTrainingContent`를 어드민이 등록해 둔
    경우 그 콘텐츠 URL을 `<video>` src로 주입한다. 미등록 시에는 기존
    `static/video/safety_vr.mp4`로 폴백되어 화면이 깨지지 않는다.

    [context 키]
    - `vr_content_id`: 클라이언트의 진행도 가드(다른 콘텐츠 position 적용
      방지)에 사용. data-content-id 속성으로 전달.
    - `vr_content_url`: <source src>에 직접 렌더.
    - `vr_content_name`: 현재 미사용이지만 향후 페이지 타이틀에 노출 여지.

    [facility 해석]
    `user.facility_id`가 NULL이면 `get_default_facility_id()` 폴백. 단일
    공장 단계에서는 정상 동작하지만 다중 공장 전환 시 작업자(worker)에게는
    폴백을 끊는 것이 안전 — 후속 정리 과제.
    """
    content_id = None
    content_url = None
    content_name = None
    user = request.user
    if user.is_authenticated:
        facility_id = getattr(user, "facility_id", None) or get_default_facility_id()
        if facility_id is not None:
            content = get_vr_content_for_facility(facility_id)
            if content is not None:
                content_id = content.id
                content_url = content.content_url
                content_name = content.name
    return render(
        request,
        "snb_details/safety_vr.html",
        {
            "vr_content_id": content_id,
            "vr_content_url": content_url,
            "vr_content_name": content_name,
        },
    )


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
    """VR 시청 위치 임시 저장 (세션).

    [user_id 가드]
    Django 세션은 브라우저 단위라 같은 PC에서 사용자 A가 보던 위치가 사용자 B
    로그인 후에도 남아 즉시 ended로 점프하는 버그가 있다. 세션에 user_id를
    함께 저장하고, GET 시 현재 인증 사용자와 일치하지 않으면 빈 값으로 응답해
    누설을 차단한다.

    [content_id 가드]
    어드민이 영상을 교체했을 때 이전 영상의 position이 새 영상에 잘못 적용되어
    검은 화면이나 즉시 종료가 일어나는 버그를 막는다. 클라이언트가 페이지의
    현재 content_id와 응답의 content_id가 일치할 때만 position을 복원한다.
    """

    permission_classes = [AllowAny]

    SESSION_KEY = "vr_safety_progress"

    def _current_user_id(self, request) -> int | None:
        return request.user.id if request.user.is_authenticated else None

    @extend_schema(
        tags=["Dashboard"],
        summary="VR 안전교육 시청 위치 조회 (세션)",
        responses={
            200: inline_serializer(
                name="VRProgressGet",
                fields={
                    "content_id": serializers.IntegerField(allow_null=True),
                    "position": serializers.FloatField(),
                },
            )
        },
    )
    def get(self, request):
        stored = request.session.get(self.SESSION_KEY) or {}
        if stored.get("user_id") != self._current_user_id(request):
            # 다른 사용자가 같은 브라우저 세션을 쓴 경우 — 진행도 누설 차단.
            return Response({"content_id": None, "position": 0})
        return Response(
            {
                "content_id": stored.get("content_id"),
                "position": stored.get("position", 0),
            }
        )

    @extend_schema(
        tags=["Dashboard"],
        summary="VR 안전교육 시청 위치 저장 (세션)",
        request=inline_serializer(
            name="VRProgressPost",
            fields={
                "content_id": serializers.IntegerField(allow_null=True),
                "position": serializers.FloatField(),
            },
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
        raw_cid = request.data.get("content_id")
        try:
            content_id = int(raw_cid) if raw_cid not in (None, "", "null") else None
        except (TypeError, ValueError):
            content_id = None
        request.session[self.SESSION_KEY] = {
            "user_id": self._current_user_id(request),
            "content_id": content_id,
            "position": position,
        }
        return Response({"saved": position})


# ──────────────────────────────────────────────────────────
# GET/POST /api/safety-status/ — 나의 안전확인 완료 상태 (세션 기반)
# ──────────────────────────────────────────────────────────
class MySafetyStatusView(APIView):
    """오늘의 안전 확인 완료 상태 — 메인 대시보드 카드용 API.

    [세션 + DB 이중 저장 — Phase 4 변경]
    POST 시점에 (1) Django 세션 키, (2) `SafetyCheckSession` DB row 두 곳에
    완료 시각을 모두 기록한다. 세션은 즉시 표시(휘발)용, DB는 이력 페이지와
    다른 기기 일관성용. GET은 세션을 먼저 확인하고 비어 있으면 DB로 폴백.

    [AllowAny 사유]
    인증된 사용자만 의미가 있지만, 익명 호출도 200 OK로 응답하도록 두어
    프런트의 fetch 흐름이 401 핸들링 없이 단순해진다. 실제 DB 기록은
    `is_authenticated`일 때만 일어남.
    """

    permission_classes = [AllowAny]

    CHECKLIST_KEY = "safety_checklist_done_date"
    VR_KEY = "safety_vr_done_date"

    def _is_done_today(self, request, key) -> bool:
        """오늘 해당 항목이 완료됐는지 — 세션 우선, DB 폴백.

        세션에 오늘 날짜가 박혀 있으면 즉시 True. 그렇지 않으면 DB의
        SafetyCheckSession을 조회해 다른 기기에서의 완료 흔적을 찾는다.
        """
        if request.session.get(key) == str(date.today()):
            return True
        return self._is_done_today_in_db(request, key)

    def _is_done_today_in_db(self, request, key) -> bool:
        """세션이 비어 있어도 DB에 오늘자 완료 기록이 있으면 True.

        [폴백 동기]
        - 다른 PC/브라우저로 로그인 → 세션은 비어 있지만 DB엔 완료가 남음
        - 세션 만료/쿠키 삭제 후 재진입 → 동일 상황

        익명 사용자에게는 항상 False (DB에 사용자 식별이 불가하므로).
        """
        if not request.user.is_authenticated:
            return False
        from apps.safety.models import SafetyCheckSession

        today = date.today()
        qs = SafetyCheckSession.objects.filter(worker=request.user, date=today)
        if key == self.CHECKLIST_KEY:
            return qs.filter(is_completed=True).exists()
        if key == self.VR_KEY:
            return qs.filter(vr_completed_at__isnull=False).exists()
        return False

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
        if key_name not in ("checklist", "vr"):
            return Response(
                {"error": "key는 'checklist' 또는 'vr'이어야 합니다."}, status=400
            )

        # 1) 기존 세션 키 — 메인 대시보드 즉시 표시용(휘발).
        today_str = str(date.today())
        if key_name == "checklist":
            request.session[self.CHECKLIST_KEY] = today_str
        else:
            request.session[self.VR_KEY] = today_str

        # 2) DB dual-write — 안전 확인 이력 페이지가 영구히 ✓로 보이게 함.
        if request.user.is_authenticated:
            self._record_completion_to_db(request.user, key_name)

        return Response({"ok": True})

    def _record_completion_to_db(self, user, key_name: str) -> None:
        """SafetyCheckSession에 완료 시각을 기록 (이력·다른 기기 일관성용).

        [기록 방식]
        - `key_name == 'checklist'`: `is_completed=True`, `completed_at=now`
        - `key_name == 'vr'`: `vr_completed_at=now`
        두 작업은 같은 (worker, date, revision) row의 다른 필드를 갱신하므로
        "오늘의 안전 확인 1회" 묶음 의미가 유지된다.

        [실패 허용]
        active Revision이 없거나 facility 미지정 등으로 세션 생성이 실패하면
        ValueError가 raise된다. 메인 대시보드 표시(세션 기반)는 이미 성공했고
        이력 페이지에 ✗로 남는 것은 어드민이 체크리스트를 발행하지 않은
        상태이므로 자연스러운 결과 — 로그만 남기고 예외를 삼킨다.
        """
        from apps.safety.services.check_service import get_or_create_today_session

        facility_id = getattr(user, "facility_id", None) or get_default_facility_id()
        if facility_id is None:
            return
        try:
            session = get_or_create_today_session(
                worker_id=user.id, facility_id=facility_id
            )
        except ValueError as exc:
            logger.info("안전 세션 생성 불가 (active revision 없음): %s", exc)
            return
        now = timezone.now()
        if key_name == "checklist":
            session.is_completed = True
            session.completed_at = now
            session.save(update_fields=["is_completed", "completed_at", "updated_at"])
        else:  # vr
            session.vr_completed_at = now
            session.save(update_fields=["vr_completed_at", "updated_at"])


# ──────────────────────────────────────────────────────────
# GET /api/safety-history/?month=YYYY-MM[&worker_id=X]
# ──────────────────────────────────────────────────────────
class SafetyHistoryAPIView(APIView):
    """월별 안전 확인 이력 캘린더 데이터.

    [데이터 소스 — Phase 4 이후]
    체크리스트/VR 완료 모두 `SafetyCheckSession` 한 모델에서 조회한다.
    한 row의 `is_completed`와 `vr_completed_at` 두 필드가 각각의 완료 상태를
    표현하므로 단일 쿼리로 두 시리즈를 동시에 채울 수 있다.

    [관리자 다른 작업자 조회]
    `?worker_id=` 파라미터로 다른 작업자의 이력을 조회 가능. SUPER_ADMIN/
    FACILITY_ADMIN(`ADMIN_TYPES`)만 허용. 일반 사용자는 본인 데이터로 강제.

    [attended 시리즈]
    출근 여부는 `LoginLog` 성공 로그인 시점 기준으로 계산. 완료 여부와 독립
    적으로 캘린더에 색칠된다.
    """

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
                                "attended": serializers.BooleanField(),
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

        from apps.accounts.models import LoginLog
        from apps.safety.models import SafetyCheckSession

        # 체크리스트/VR 완료 모두 SafetyCheckSession 1개 row에 기록되어 있다.
        sessions = SafetyCheckSession.objects.filter(
            worker=target,
            date__year=year,
            date__month=month,
        ).values("date", "is_completed", "vr_completed_at")
        checklist_dates = {s["date"] for s in sessions if s["is_completed"]}
        vr_dates = {s["date"] for s in sessions if s["vr_completed_at"] is not None}

        attended_dates = set(
            LoginLog.objects.filter(
                user=target,
                login_result=LoginLog.LoginResult.SUCCESS,
                timestamp__year=year,
                timestamp__month=month,
            )
            .values_list("timestamp__date", flat=True)
            .distinct()
        )

        _, days_in_month = calendar.monthrange(year, month)
        records = []
        for day in range(1, days_in_month + 1):
            d = date(year, month, day)
            records.append(
                {
                    "date": d.isoformat(),
                    "attended": d in attended_dates,
                    "checklist_done": d in checklist_dates,
                    "vr_done": d in vr_dates,
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
            "facility_admin은 자기 공장 사용자만, super_admin은 전체 활성 사용자. "
            "오늘 LoginLog 성공 기록 유무로 `is_present` 자동 계산."
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

        from django.utils import timezone

        from apps.accounts.models import CustomUser, Department, LoginLog

        workers = CustomUser.objects.filter(deactivated_at__isnull=True)

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

        today = timezone.localdate()
        today_logins = LoginLog.objects.filter(
            user=OuterRef("pk"),
            login_result=LoginLog.LoginResult.SUCCESS,
            timestamp__date=today,
        )
        workers = (
            workers.annotate(is_present=Exists(today_logins))
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
                    memberships__user__deactivated_at__isnull=True,
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
