"""
apps/alerts/serializers/responses.py

알람·이벤트 도메인의 표준 응답 봉투 Serializer.

이 모듈의 클래스들은 (1) Swagger 문서화, (2) 실제 응답 직렬화 양쪽에서 재사용 가능하다.
공통 봉투 패턴: `{status: "success", code: 200, data: {...}}`
"""

from rest_framework import serializers


# ============================================================
# 작업자 본인 위험도 (MyStatusView)
# ============================================================


class MyStatusDataSerializer(serializers.Serializer):
    worker_id = serializers.IntegerField()
    status = serializers.CharField(help_text="normal / warning / danger")
    active_risk_level = serializers.CharField(
        allow_null=True, help_text="미해결 이벤트 중 최댓값 위험도, 없으면 null"
    )


class MyStatusResponseSerializer(serializers.Serializer):
    status = serializers.CharField(help_text='고정값 "success"')
    code = serializers.IntegerField(help_text="HTTP 상태와 동일한 정수")
    data = MyStatusDataSerializer()


# ============================================================
# 공장 내 작업자 위험도 집계 (WorkerSummaryView)
# ============================================================


class WorkerSummaryDataSerializer(serializers.Serializer):
    facility_id = serializers.IntegerField(allow_null=True)
    total_count = serializers.IntegerField()
    normal_count = serializers.IntegerField()
    warning_count = serializers.IntegerField()
    danger_count = serializers.IntegerField()


class WorkerSummaryResponseSerializer(serializers.Serializer):
    status = serializers.CharField(help_text='고정값 "success"')
    code = serializers.IntegerField(help_text="HTTP 상태와 동일한 정수")
    data = WorkerSummaryDataSerializer()
