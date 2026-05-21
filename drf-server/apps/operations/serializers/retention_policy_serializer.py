"""
operations/serializers/retention_policy_serializer.py

DataRetentionPolicy 조회/수정용 시리얼라이저.

[읽기]
  device_type_display, data_category_display, delete_cycle_display —
  TextChoices 한글 라벨을 함께 내려 JS에서 별도 매핑 없이 바로 렌더링 가능.

[쓰기 (PATCH)]
  수정 허용 필드: raw_retention_days, history_retention_days, delete_cycle, is_active, memo
  수정 불가 필드: device_type, data_category (데이터 카테고리 변경은 정책 자체를 바꾸는 것)

[validate]
  history_retention_days >= raw_retention_days 강제 —
  집계 이력은 원천보다 오래 보관해야 원천 삭제 후 이력이 남는다.
"""

from rest_framework import serializers

from apps.operations.models.data_retention_policy import DataRetentionPolicy


class DataRetentionPolicySerializer(serializers.ModelSerializer):
    # TextChoices 한글 라벨 — 화면에서 별도 매핑 불필요
    device_type_display = serializers.CharField(
        source="get_device_type_display", read_only=True
    )
    data_category_display = serializers.CharField(
        source="get_data_category_display", read_only=True
    )
    delete_cycle_display = serializers.CharField(
        source="get_delete_cycle_display", read_only=True
    )

    class Meta:
        model = DataRetentionPolicy
        fields = [
            "id",
            "device_type",
            "device_type_display",
            "data_category",
            "data_category_display",
            "raw_retention_days",
            "history_retention_days",
            "delete_cycle",
            "delete_cycle_display",
            "is_active",
            "memo",
            "updated_at",
        ]
        # device_type, data_category — 카테고리 식별자이므로 수정 불가
        read_only_fields = ["device_type", "data_category", "updated_at"]

    def validate(self, data):
        """
        이력 보관 기간 >= 원천 보관 기간 강제.

        PATCH 시 한쪽만 수정될 수 있으므로 instance의 현재 값을 fallback으로 사용.
        """
        instance = self.instance
        raw = data.get(
            "raw_retention_days",
            instance.raw_retention_days if instance else None,
        )
        history = data.get(
            "history_retention_days",
            instance.history_retention_days if instance else None,
        )
        if raw is not None and history is not None and history < raw:
            raise serializers.ValidationError(
                "이력 보관 기간(history_retention_days)은 "
                "원천 보관 기간(raw_retention_days) 이상이어야 합니다."
            )
        return data
