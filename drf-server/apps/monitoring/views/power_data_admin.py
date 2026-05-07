"""
apps/monitoring/views/power_data_admin.py

전력 측정 데이터 관리 어드민 API 뷰 3개를 정의한다.

  PowerDataAdminListView       — 필터 + 페이지네이션이 적용된 목록 JSON 반환
  PowerDataAdminExportView     — 동일 필터로 전체 데이터를 CSV 파일로 반환 (페이지네이션 없음)
  PowerDataAdminDeviceListView — 장비 드롭다운용 활성 전력 장비 목록 반환

URL은 apps/monitoring/admin_urls.py 에 등록되며,
실제 접근 경로는 /api/admin/power-data/ (config/urls.py 참고)
"""

import csv
from datetime import datetime
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdmin
from apps.monitoring.models import PowerData
from apps.facilities.models.devices import PowerDevice


DATA_TYPE_LABELS = {
    "current": "전류 (A)",
    "voltage": "전압 (V)",
    "watt": "전력 (W)",
}

VALID_ORDERINGS = ["received_at", "-received_at"]
VALID_DATA_TYPES = ["current", "voltage", "watt"]


def _parse_datetime(value: str):
    """
    'YYYY-MM-DDTHH:MM' 또는 'YYYY-MM-DD' 문자열을 timezone-aware datetime으로 변환.
    파싱 실패 시 None 반환.
    """
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return timezone.make_aware(datetime.strptime(value, fmt))
        except ValueError:
            continue
    return None


def _build_queryset(params):
    """
    쿼리 파라미터를 받아 PowerData ORM 쿼리셋을 반환한다.

    이 함수는 PowerDataAdminListView(목록)와 PowerDataAdminExportView(CSV 내보내기)
    양쪽에서 공통으로 호출된다.

    적용 필터:
      device    — power_device_id 일치 (없으면 전체 장비)
      data_type — current / voltage / watt (없으면 전체 종류)
      date_from — received_at 시작 datetime (포함, YYYY-MM-DDTHH:MM 또는 YYYY-MM-DD)
      date_to   — received_at 종료 datetime (포함, YYYY-MM-DDTHH:MM 또는 YYYY-MM-DD)
      ordering  — received_at 오름/내림차순 (기본: 최신순 -received_at)
    """
    qs = PowerData.objects.select_related("power_device")

    device_id = params.get("device", "").strip()
    if device_id:
        qs = qs.filter(power_device_id=device_id)

    data_type = params.get("data_type", "").strip()
    if data_type in VALID_DATA_TYPES:
        qs = qs.filter(data_type=data_type)

    dt_from = _parse_datetime(params.get("date_from", "").strip())
    if dt_from:
        qs = qs.filter(received_at__gte=dt_from)

    dt_to = _parse_datetime(params.get("date_to", "").strip())
    if dt_to:
        qs = qs.filter(received_at__lte=dt_to)

    ordering = params.get("ordering", "-received_at")
    if ordering not in VALID_ORDERINGS:
        ordering = "-received_at"
    qs = qs.order_by(ordering)

    return qs


def _serialize_row(obj):
    """PowerData ORM 인스턴스 1건을 프론트엔드용 딕셔너리로 변환한다."""
    return {
        "id": obj.id,
        "received_at": timezone.localtime(obj.received_at).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "device_name": obj.power_device.device_name,
        "channel": obj.channel,
        "data_type": obj.data_type,
        "data_type_label": DATA_TYPE_LABELS.get(obj.data_type, obj.data_type),
        "value": round(obj.value, 2) if obj.value is not None else None,
        "risk_level": obj.risk_level,
    }


class PowerDataAdminListView(APIView):
    """
    GET /api/admin/power-data/

    전력 측정 데이터 목록을 페이지네이션과 함께 반환한다.
    쿼리 파라미터:
      device     — 장비 ID (PowerDevice.id)
      data_type  — current / voltage / watt
      date_from  — 조회 시작 datetime (YYYY-MM-DDTHH:MM 또는 YYYY-MM-DD)
      date_to    — 조회 종료 datetime (YYYY-MM-DDTHH:MM 또는 YYYY-MM-DD)
      ordering   — received_at / -received_at (기본: -received_at)
      page       — 페이지 번호 (기본: 1)
      page_size  — 페이지당 행 수 (기본: 20, 최대: 100)
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Power Data"],
        summary="전력 측정 데이터 목록 조회",
        parameters=[
            OpenApiParameter(
                name="device", type=int, required=False, description="PowerDevice.id"
            ),
            OpenApiParameter(
                name="data_type",
                type=str,
                required=False,
                description="current | voltage | watt",
            ),
            OpenApiParameter(name="date_from", type=str, required=False),
            OpenApiParameter(name="date_to", type=str, required=False),
            OpenApiParameter(name="ordering", type=str, required=False),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="PowerDataRow",
                fields={
                    "id": serializers.IntegerField(),
                    "received_at": serializers.CharField(),
                    "device_name": serializers.CharField(),
                    "channel": serializers.IntegerField(),
                    "data_type": serializers.CharField(),
                    "data_type_label": serializers.CharField(),
                    "value": serializers.FloatField(allow_null=True),
                    "risk_level": serializers.CharField(),
                },
                many=True,
            ),
        },
    )
    def get(self, request):
        qs = _build_queryset(request.query_params)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response([_serialize_row(o) for o in page])


class PowerDataAdminExportView(APIView):
    """
    GET /api/admin/power-data/export/

    현재 필터 조건에 해당하는 모든 전력 데이터를 CSV 파일로 반환한다.
    utf-8-sig(BOM) 인코딩으로 엑셀 한글 깨짐 방지.
    qs.iterator(chunk_size=500)으로 대용량 데이터 메모리 절약.
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Power Data"],
        summary="전력 측정 데이터 CSV 다운로드",
        parameters=[
            OpenApiParameter(name="device", type=int, required=False),
            OpenApiParameter(name="data_type", type=str, required=False),
            OpenApiParameter(name="date_from", type=str, required=False),
            OpenApiParameter(name="date_to", type=str, required=False),
            OpenApiParameter(name="ordering", type=str, required=False),
        ],
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: OpenApiResponse(description="CSV 파일 (text/csv)"),
        },
    )
    def get(self, request):
        qs = _build_queryset(request.query_params)

        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = 'attachment; filename="power_data_export.csv"'

        writer = csv.writer(response)
        writer.writerow(
            ["수집 시각", "장비명", "채널", "측정 종류", "측정값", "위험도"]
        )

        for obj in qs.iterator(chunk_size=500):
            writer.writerow(
                [
                    timezone.localtime(obj.received_at).strftime("%Y-%m-%d %H:%M:%S"),
                    obj.power_device.device_name,
                    obj.channel,
                    DATA_TYPE_LABELS.get(obj.data_type, obj.data_type),
                    round(obj.value, 2) if obj.value is not None else "",
                    obj.risk_level,
                ]
            )

        return response


class PowerDataAdminDeviceListView(APIView):
    """
    GET /api/admin/power-data/devices/

    장비 드롭다운 옵션용 활성 전력 장비 목록을 반환한다.
    is_active=True인 장비만 반환하며 device_name 기준 오름차순 정렬.
    응답: [ { id, device_name, device_id }, ... ]
    """

    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=["Admin — Power Data"],
        summary="활성 전력 장비 드롭다운 옵션",
        responses={
            401: OpenApiResponse(description="인증 필요 (토큰 누락/만료)"),
            200: inline_serializer(
                name="PowerDeviceOption",
                fields={
                    "id": serializers.IntegerField(),
                    "device_name": serializers.CharField(),
                    "device_id": serializers.CharField(),
                },
                many=True,
            ),
        },
    )
    def get(self, request):
        devices = (
            PowerDevice.objects.filter(is_active=True)
            .values("id", "device_name", "device_id")
            .order_by("device_name")
        )
        return Response(list(devices))
