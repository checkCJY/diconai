"""
apps/monitoring/views/gas_data_admin.py

유해가스 센서 데이터 관리 어드민 API 뷰 3개를 정의한다.

  GasDataAdminListView   — 필터 + 페이지네이션이 적용된 목록 JSON 반환
  GasDataAdminExportView — 동일 필터로 전체 데이터를 CSV 파일로 반환 (페이지네이션 없음)
  GasDataAdminSensorListView — 센서 드롭다운용 활성 센서 목록 반환

URL은 apps/monitoring/urls.py 에 등록되며,
실제 접근 경로는 /api/admin/gas-data/ (config/urls.py 참고)
"""

import csv
from datetime import datetime
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.core.pagination import AdminPagination
from apps.core.permissions import IsSuperAdmin
from apps.monitoring.models import GasData
from apps.facilities.models.devices import GasSensor


# 가스 9종 컬럼 순서 — 테이블 헤더 및 CSV 컬럼 순서와 일치시켜야 한다.
# 이 리스트를 바꾸면 HTML 테이블 헤더(gas_data.html)와 JS 렌더 로직(gas_data.js)도 같이 바꿔야 한다.
GAS_COLS = ["co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"]

# CSV 헤더 표시용 한글+단위 레이블. GAS_COLS 순서와 반드시 1:1 대응.
GAS_LABELS = {
    "co": "CO (ppm)",
    "h2s": "H2S (ppm)",
    "co2": "CO2 (ppm)",
    "o2": "O2 (%)",
    "no2": "NO2 (ppm)",
    "so2": "SO2 (ppm)",
    "o3": "O3 (ppm)",
    "nh3": "NH3 (ppm)",
    "voc": "VOC (ppm)",
}

# 허용 정렬 값 화이트리스트 — SQL Injection 방어 및 의도치 않은 인덱스 회피용
VALID_ORDERINGS = ["received_at", "-received_at"]


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
    쿼리 파라미터를 받아 GasData ORM 쿼리셋을 반환한다.

    이 함수는 GasDataAdminListView(목록)와 GasDataAdminExportView(CSV 내보내기)
    양쪽에서 공통으로 호출된다. 필터 로직을 한 곳에만 두기 위해 분리했다.

    적용 필터:
      sensor    — gas_sensor_id 일치 (없으면 전체 센서)
      date_from — received_at 시작 datetime (포함, YYYY-MM-DDTHH:MM 또는 YYYY-MM-DD)
      date_to   — received_at 종료 datetime (포함, YYYY-MM-DDTHH:MM 또는 YYYY-MM-DD)
      ordering  — received_at 오름/내림차순 (기본: 최신순 -received_at)
    """
    qs = GasData.objects.select_related("gas_sensor")

    sensor_id = params.get("sensor", "").strip()
    if sensor_id:
        qs = qs.filter(gas_sensor_id=sensor_id)

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
    """
    GasData ORM 인스턴스 1건을 프론트엔드용 딕셔너리로 변환한다.

    호출 위치: GasDataAdminListView.get() 안에서 results 배열을 만들 때.
    CSV 내보내기는 이 함수를 사용하지 않는다 — CSV는 iterator() 기반으로
    직접 writer.writerow()를 호출해 메모리를 절약한다.

    received_at은 timezone.localtime()으로 서버 로컬 시간대로 변환 후 포맷.
    가스 값은 None(결측)이면 그대로 None을 내려 프론트에서 "-"로 표시한다.
    """
    row = {
        "id": obj.id,
        "received_at": timezone.localtime(obj.received_at).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "sensor_name": obj.gas_sensor.device_name,
        "max_risk_level": obj.max_risk_level,
    }
    for col in GAS_COLS:
        val = getattr(obj, col)
        row[col] = round(val, 2) if val is not None else None
    return row


class GasDataAdminListView(APIView):
    """
    GET /api/admin/gas-data/

    유해가스 측정 데이터 목록을 페이지네이션과 함께 반환한다.
    쿼리 파라미터:
      sensor     — 센서 ID (GasSensor.id)
      date_from  — 조회 시작일 (YYYY-MM-DD)
      date_to    — 조회 종료일 (YYYY-MM-DD)
      ordering   — received_at / -received_at (기본: -received_at)
      page       — 페이지 번호 (기본: 1)
      page_size  — 페이지당 행 수 (기본: 20, 최대: 100)

    응답 형태:
      { total, page, page_size, results: [ {id, received_at, sensor_name, co, ...}, ... ] }

    total은 현재 필터 기준 전체 건수이므로 프론트에서 전체 페이지 수 계산에 사용한다.
    페이지네이션은 AdminPagination(공용)이 LIMIT/OFFSET SQL로 변환한다.
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        qs = _build_queryset(request.query_params)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response([_serialize_row(o) for o in page])


class GasDataAdminExportView(APIView):
    """
    GET /api/admin/gas-data/export/

    현재 필터 조건에 해당하는 모든 가스 데이터를 CSV 파일로 반환한다.
    페이지네이션 없이 전체 행을 한 번에 내보낸다.

    쿼리 파라미터: GasDataAdminListView와 동일 (page/page_size 제외)

    핵심 동작 원리:
      1. _build_queryset()으로 목록 API와 동일한 필터를 적용한다.
         → 사용자가 화면에서 보는 필터와 CSV가 항상 같은 데이터를 보장.
      2. HttpResponse에 content_type="text/csv; charset=utf-8-sig" 를 지정한다.
         utf-8-sig = BOM 포함 UTF-8 → 엑셀에서 한글이 깨지지 않도록 하기 위함.
      3. Content-Disposition 헤더로 브라우저가 파일 다운로드로 처리하게 한다.
      4. qs.iterator(chunk_size=500)를 사용해 대용량 데이터도 메모리에 한꺼번에
         올리지 않고 500건씩 DB에서 가져와 스트리밍 방식으로 CSV에 쓴다.
         (일반 qs 평가는 전체를 메모리에 올리므로 데이터가 많으면 OOM 위험)
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        qs = _build_queryset(request.query_params)

        # BOM(utf-8-sig)을 붙여야 엑셀에서 한글 깨짐 없이 열린다
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = 'attachment; filename="gas_data_export.csv"'

        writer = csv.writer(response)

        # CSV 헤더 행: 수신 시각, 장비명, 가스 9종(한글 레이블), 최고 위험도
        writer.writerow(
            ["수신 시각", "장비명"]
            + [GAS_LABELS[c] for c in GAS_COLS]
            + ["최고 위험도"]
        )

        # iterator()로 500건씩 DB에서 가져와 바로 CSV에 기록 (메모리 절약)
        for obj in qs.iterator(chunk_size=500):
            row_vals = [
                timezone.localtime(obj.received_at).strftime("%Y-%m-%d %H:%M:%S"),
                obj.gas_sensor.device_name,
            ]
            for col in GAS_COLS:
                val = getattr(obj, col)
                row_vals.append(round(val, 2) if val is not None else "")
            row_vals.append(obj.max_risk_level)
            writer.writerow(row_vals)

        return response


class GasDataAdminSensorListView(APIView):
    """
    GET /api/admin/gas-data/sensors/

    센서 드롭다운 옵션용 활성 가스 센서 목록을 반환한다.
    페이지 첫 로드 시 JS가 이 엔드포인트를 호출해 <select> 옵션을 채운다.

    is_active=True인 센서만 반환하며 device_name 기준 오름차순 정렬.
    응답: [ { id, device_name, device_id }, ... ]
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        sensors = (
            GasSensor.objects.filter(is_active=True)
            .values("id", "device_name", "device_id")
            .order_by("device_name")
        )
        return Response(list(sensors))
