"""어드민 패널 — 알림 정책 관리 시리얼라이저 모음.

List/Detail/Create/Update 4종. 목록 화면(List)·등록 팝업(Create)·수정 팝업(Update)·
상세 조회(Detail) 가 각자 다른 schema 를 가짐.
"""

from rest_framework import serializers

from apps.alerts.models import AlertPolicy
from apps.alerts.services.policy_matcher import compute_condition_summary, save_policy


class AlertPolicyListSerializer(serializers.ModelSerializer):
    """목록 테이블 1행 직렬화 — 화면 컬럼: 정책명·이벤트 상세·발송 채널·수신 대상·
    사용 여부·적용 조건 요약."""

    event_type_display = serializers.CharField(
        source="get_event_type_display", read_only=True
    )
    # DB 캐시 (save_policy 가 채움) 가 비어있으면 즉석 계산.
    condition_summary = serializers.SerializerMethodField()

    class Meta:
        model = AlertPolicy
        fields = [
            "id",
            "name",
            "event_type",
            "event_type_display",
            "channels",
            "target_user_types",
            "is_active",
            "condition_summary",
            "updated_at",
        ]

    def get_condition_summary(self, obj):
        return obj.condition_summary or compute_condition_summary(obj)


class AlertPolicyDetailSerializer(serializers.ModelSerializer):
    """상세 조회 — 등록·수정 폼이 prefill 할 전체 필드."""

    event_type_display = serializers.CharField(
        source="get_event_type_display", read_only=True
    )
    policy_kind_display = serializers.CharField(
        source="get_policy_kind_display", read_only=True
    )
    condition_summary = serializers.SerializerMethodField()

    class Meta:
        model = AlertPolicy
        fields = [
            "id",
            "name",
            "event_type",
            "event_type_display",
            "policy_kind",
            "policy_kind_display",
            "target_facility",
            "target_user_types",
            "target_sensor_ids",
            "target_device_ids",
            "target_geofence_ids",
            "channels",
            "condition_summary",
            "message_template",
            "recommended_actions",
            "is_active",
            "description",
            "created_at",
            "updated_at",
        ]

    def get_condition_summary(self, obj):
        return obj.condition_summary or compute_condition_summary(obj)


class AlertPolicyWriteSerializer(serializers.ModelSerializer):
    """Create/Update 공용 — partial=True 로 PATCH 처리.

    저장 시 [[policy_matcher.save_policy]] 경유 → condition_summary 자동 갱신 +
    매처 캐시 무효화 (운영자 변경 즉시 반영).
    """

    class Meta:
        model = AlertPolicy
        fields = [
            "name",
            "event_type",
            "policy_kind",
            "target_facility",
            "target_user_types",
            "target_sensor_ids",
            "target_device_ids",
            "target_geofence_ids",
            "channels",
            "message_template",
            "recommended_actions",
            "is_active",
            "description",
        ]

    def validate_recommended_actions(self, value):
        """dict 키는 RiskLevel(danger/warning) 또는 "default" 만 허용. 값은 문자열 리스트."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("dict 형태여야 합니다.")
        allowed_keys = {"danger", "warning", "default"}
        for key, steps in value.items():
            if key not in allowed_keys:
                raise serializers.ValidationError(
                    f"허용되지 않은 키: {key!r}. 허용: {sorted(allowed_keys)}"
                )
            if not isinstance(steps, list) or not all(
                isinstance(s, str) for s in steps
            ):
                raise serializers.ValidationError(
                    f"{key!r} 값은 문자열 리스트여야 합니다."
                )
        return value

    def create(self, validated_data):
        instance = AlertPolicy(**validated_data)
        return save_policy(instance)

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        return save_policy(instance)
