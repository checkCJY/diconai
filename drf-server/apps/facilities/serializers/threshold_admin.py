"""facilities/serializers/threshold_admin.py

임계치 기준 관리 어드민 API 시리얼라이저.

ThresholdGroup (분류 그룹) 과 Threshold (임계치 항목) 각각 읽기/쓰기 분리.
facility FK 는 관리자 화면에서 다루지 않음 — 전사 기준(facility=null)만 대상.
"""

from rest_framework import serializers

from apps.facilities.models.thresholds import Threshold, ThresholdGroup


class ThresholdGroupSerializer(serializers.ModelSerializer):
    """분류 그룹 읽기 시리얼라이저 — 목록·상세 공용."""

    # 그룹에 속한 임계치 수 (우측 패널 정보 표시용)
    threshold_count = serializers.IntegerField(
        source="thresholds.count", read_only=True
    )

    class Meta:
        model = ThresholdGroup
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_active",
            "apply_scope",      # 반영 범위 (realtime/ai/alert 목록)
            "threshold_count",
            "updated_at",
        ]


class ThresholdGroupWriteSerializer(serializers.ModelSerializer):
    """분류 그룹 등록·수정 시리얼라이저."""

    class Meta:
        model = ThresholdGroup
        fields = ["code", "name", "description", "is_active", "apply_scope"]

    def validate_code(self, value):
        """code 는 소문자·숫자·언더스코어만 허용 (모델 수준 unique 도 체크됨)."""
        import re
        if not re.match(r"^[a-z][a-z0-9_]*$", value):
            raise serializers.ValidationError(
                "코드는 소문자·숫자·언더스코어만 사용 가능합니다. (예: gas_legal)"
            )
        return value

    def validate_apply_scope(self, value):
        """반영 범위는 realtime/ai/alert 값만 허용."""
        allowed = {"realtime", "ai", "alert"}
        if not isinstance(value, list):
            raise serializers.ValidationError("리스트 형식이어야 합니다.")
        invalid = set(value) - allowed
        if invalid:
            raise serializers.ValidationError(f"허용되지 않는 값: {invalid}")
        return value


class ThresholdSerializer(serializers.ModelSerializer):
    """임계치 항목 읽기 시리얼라이저 — 목록·상세 공용."""

    # 판단조건 한글 표시 (예: "초과", "이상")
    condition_type_display = serializers.CharField(
        source="get_condition_type_display", read_only=True
    )

    class Meta:
        model = Threshold
        fields = [
            "id",
            "measurement_item",        # 측정항목 (예: co, h2s)
            "unit",                    # 단위 (예: ppm)
            "condition_type",          # 판단조건 코드 (gt/gte/lt/lte)
            "condition_type_display",  # 판단조건 한글
            "warning_min",             # 주의 최솟값
            "warning_max",             # 주의 최댓값
            "danger_min",              # 위험 최솟값
            "danger_max",              # 위험 최댓값
            "chart_max",               # 차트 Y축 최댓값
            "description",
            "is_active",
            "updated_at",
        ]


class ThresholdWriteSerializer(serializers.ModelSerializer):
    """임계치 항목 등록·수정 시리얼라이저.

    facility 는 null 고정 (전사 기준) — 클라이언트에서 받지 않음.
    group 은 URL 경로(/threshold-groups/<id>/thresholds/)에서 주입.
    """

    class Meta:
        model = Threshold
        fields = [
            "measurement_item",
            "unit",
            "condition_type",  # 판단조건
            "warning_min",
            "warning_max",
            "danger_min",
            "danger_max",
            "chart_max",
            "description",
            "is_active",
        ]
