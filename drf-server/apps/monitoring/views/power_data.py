# monitoring/views/power_data.py
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.authentication import ServiceTokenAuthentication
from apps.core.constants import GasTypeChoices
from apps.facilities.services.threshold_service import get_threshold
from apps.monitoring.serializers.power_data import (
    PowerDataBulkIngestSerializer,
    PowerEventIngestSerializer,
)


def _to_float(value):
    """Decimal/None → float/None (JSON 직렬화 호환)."""
    return float(value) if value is not None else None


class GasThresholdView(APIView):
    """
    GET /api/monitoring/gas/thresholds/

    가스 9종 임계치 dict 반환. 프론트엔드 차트의 임계 라인·칩 라벨 위치 결정용.
    공개 데이터 (PowerThresholdView 와 동일 정책).

    [단일 진실 공급원]
    Threshold(group_code="gas_legal") DB 조회. 어드민에서 변경 시 다음 요청부터
    반영 (signal 기반 invalidate).

    [응답 형식]
        {
            "co":  {"warning_min": null, "warning_max": 25.0,
                    "danger_min": null,  "danger_max": 200.0,
                    "chart_max": null, "unit": "ppm"},
            "o2":  {"warning_min": 18.0, "warning_max": 23.5,
                    "danger_min": 16.0,  "danger_max": null,
                    "chart_max": null, "unit": "%"},
            ...
        }

    o2 처럼 양방향 (warning_min + warning_max 모두 있음) 가스도 동일 형식. FE 가
    chart_max null 시 자체 fallback (예: warning_max × 1.5) 계산.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Monitoring (Public)"],
        summary="가스 9종 임계치 조회",
        description="gas_legal 그룹의 9종 임계치를 gas_code → dict 매핑으로 반환.",
        responses={200: OpenApiResponse(description="gas_code → threshold dict")},
    )
    def get(self, request):
        result = {}
        for code in GasTypeChoices.values:
            t = get_threshold("gas_legal", code) or {}
            result[code] = {
                "warning_min": _to_float(t.get("warning_min")),
                "warning_max": _to_float(t.get("warning_max")),
                "danger_min": _to_float(t.get("danger_min")),
                "danger_max": _to_float(t.get("danger_max")),
                "chart_max": _to_float(t.get("chart_max")),
                "unit": t.get("unit"),
            }
        return Response(result)


class PowerThresholdView(APIView):
    """
    GET /monitoring/api/power/thresholds/

    전력 임계치(W)를 반환한다. 프론트엔드 차트 주석 라인 및 위험도 판정에 사용.
    공개 데이터이므로 인증 불필요.

    [단일 진실 공급원]
    Threshold(group_code="power_default", measurement_item="power_w") DB 조회.
    어드민에서 변경 시 다음 요청부터 반영 (Redis 캐시 1시간 TTL + signal invalidate).
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Monitoring (Public)"],
        summary="전력 임계치(W) 조회",
        description="채널별 주의/위험 임계치(W) + 차트 Y축 최대값. DB Threshold 기반 응답.",
        responses={
            200: inline_serializer(
                name="PowerThresholds",
                fields={
                    "caution": serializers.FloatField(help_text="주의 임계치 (W)"),
                    "danger": serializers.FloatField(help_text="위험 임계치 (W)"),
                    "maxY": serializers.FloatField(help_text="차트 Y축 최대값 (W)"),
                    "unit": serializers.CharField(help_text="단위"),
                },
            )
        },
    )
    def get(self, request):
        threshold = get_threshold("power_default", "power_w") or {}
        return Response(
            {
                "caution": _to_float(threshold.get("warning_max")),
                "danger": _to_float(threshold.get("danger_max")),
                "maxY": _to_float(threshold.get("chart_max")),
                "unit": threshold.get("unit", "W"),
            }
        )


class PowerThresholdMetaView(APIView):
    """
    GET /api/monitoring/power/threshold-meta/

    fastapi-server 가 5분 주기로 sync 해 단일 결정자로서 정적 임계치 평가에 사용
    (T4 sub-plan §3.1). PowerThresholdView 는 frontend 차트용 W 절대값 (단일 항목)
    만 반환 — 본 view 는 fastapi 알람 판정에 필요한 `power_facility_default` 그룹의
    정격 % 임계치 3종을 한 응답으로 묶어 반환한다.

    [응답 형식]
        {
            "power_w":  {"warning_min": null, "warning_max": 80.0,
                          "danger_min":  null, "danger_max":  100.0, "unit": "%"},
            "current":  {...},
            "voltage":  {"warning_min": 95.0, "warning_max": 105.0,
                          "danger_min":  90.0, "danger_max":  110.0, "unit": "%"},
        }

    [단일 진실 공급원]
    Threshold(group_code="power_facility_default", measurement_item in {"power_w",
    "current", "voltage"}). 어드민 변경 시 다음 fastapi sync 주기에 반영
    (최대 5분 lag). 운영자가 admin 에서 % 수정 → DRF Redis 캐시 invalidate
    (post_save signal) → 다음 fastapi sync 응답이 신규 값을 read.

    공개 데이터 — Threshold/ChannelMeta 와 동일 정책 (AllowAny).
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Monitoring (Public)"],
        summary="전력 임계치 메타 조회 (정격 % — fastapi sync 용)",
        description=(
            "power_facility_default 그룹의 정격 % 임계치 3종 (power_w/current/voltage). "
            "fastapi-server 가 5분 주기로 sync 해 알람 판정에 사용."
        ),
        responses={200: OpenApiResponse(description="항목명 → 임계치 dict")},
    )
    def get(self, request):
        items = ("power_w", "current", "voltage")
        payload = {}
        for item in items:
            threshold = get_threshold("power_facility_default", item)
            if threshold is None:
                continue
            payload[item] = {
                "warning_min": _to_float(threshold.get("warning_min")),
                "warning_max": _to_float(threshold.get("warning_max")),
                "danger_min": _to_float(threshold.get("danger_min")),
                "danger_max": _to_float(threshold.get("danger_max")),
                "unit": threshold.get("unit", "%"),
            }
        return Response(payload)


class PowerChannelMetaView(APIView):
    """
    GET /api/monitoring/power/channel-meta/

    활성 PowerDevice 16채널 라벨·정격을 반환. fastapi-server가 broadcast 페이로드
    조립 시 채널명·정격 % 환산에 사용. 공개 데이터 (Threshold와 동일 정책).

    [응답 형식]
        {
            "<device_id>": {
                "<channel_number>": {"name": str, "rated_w": int, "rated_a": int, "rated_v": int},
                ...
            },
            ...
        }

    [단일 진실 공급원]
    PowerDevice.channel_meta JSON. 어드민 변경 시 다음 fetch 주기에 반영
    (fastapi 5분 캐시).
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Monitoring (Public)"],
        summary="전력 채널 메타 조회 (라벨 + 정격)",
        description="활성 PowerDevice의 channel_meta JSON을 device_id 단위로 묶어 반환.",
        responses={200: OpenApiResponse(description="device_id → channel_meta 매핑")},
    )
    def get(self, request):
        from apps.facilities.models import PowerDevice

        payload = {}
        for device in PowerDevice.objects.filter(is_active=True):
            payload[device.device_id] = device.channel_meta or {}
        return Response(payload)


class PowerEventIngestView(APIView):
    """
    POST /monitoring/api/power/event/

    FastAPI로부터 ON/OFF 스냅샷(PowerEvent) 수신.
    요청 바디: { device_id, measured_at, snapshot }
    응답: { "id": <PowerEvent.id> }

    서버-서버(fastapi → drf) 호출 전용 ingest 엔드포인트.
    settings.INTERNAL_SERVICE_TOKEN 설정 시 Bearer 토큰 검증 (Phase 5),
    미설정 시 기존 무인증 동작 유지 (옵트인).
    """

    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Monitoring (Ingest)"],
        summary="전력 ON/OFF 스냅샷 인입 (FastAPI → DRF)",
        description="FastAPI(:8001)가 16채널 ON/OFF 변화 스냅샷을 PowerEvent로 영속화. 무인증 서버-서버 전용.",
        request=PowerEventIngestSerializer,
        responses={
            201: inline_serializer(
                name="PowerEventIngestResponse",
                fields={"id": serializers.IntegerField()},
            ),
            400: OpenApiResponse(description="검증 실패"),
        },
    )
    def post(self, request):
        s = PowerEventIngestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        event = s.save()
        return Response({"id": event.id}, status=status.HTTP_201_CREATED)


class PowerDataBulkIngestView(APIView):
    """
    POST /monitoring/api/power/data/

    FastAPI로부터 전류/전압/전력 16채널 데이터(PowerData) 일괄 수신.
    요청 바디: { device_id, measured_at, data_type, channels: [...] }
    응답: { "created": <저장된 행 수> }

    서버-서버(fastapi → drf) 호출 전용 ingest 엔드포인트.
    settings.INTERNAL_SERVICE_TOKEN 설정 시 Bearer 토큰 검증 (Phase 5),
    미설정 시 기존 무인증 동작 유지 (옵트인).
    """

    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Monitoring (Ingest)"],
        summary="전력 16채널 측정값 일괄 인입 (FastAPI → DRF)",
        description=(
            "전류(A) / 전압(V) / 전력(W) 측정값 16채널을 한 번에 PowerData로 영속화. "
            "data_type 필드로 측정 종류 구분. 무인증 서버-서버 전용."
        ),
        request=PowerDataBulkIngestSerializer,
        responses={
            201: inline_serializer(
                name="PowerDataBulkIngestResponse",
                fields={"created": serializers.IntegerField(help_text="저장된 행 수")},
            ),
            400: OpenApiResponse(description="검증 실패"),
        },
        examples=[
            OpenApiExample(
                "전력(W) 측정값 16채널",
                description="data_type='watt'인 경우. 채널 -1 값은 통신 불능 채널(저장은 됨)",
                value={
                    "device_id": "power_01",
                    "measured_at": "2026-05-06T17:00:00Z",
                    "data_type": "watt",
                    "channels": [
                        {"channel": 1, "value": 1850},
                        {"channel": 2, "value": 1620},
                        {"channel": 3, "value": -1},
                        {"channel": 4, "value": 2100},
                    ],
                },
                request_only=True,
            ),
            OpenApiExample(
                "정상 응답",
                value={"created": 16},
                response_only=True,
                status_codes=["201"],
            ),
        ],
    )
    def post(self, request):
        s = PowerDataBulkIngestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rows = s.save()
        return Response({"created": len(rows)}, status=status.HTTP_201_CREATED)
