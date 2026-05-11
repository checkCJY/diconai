# safety/serializers/checklist_admin.py
"""
어드민 — 작업 전 안전 점검 체크리스트 관리 직렬화.
페이지: /admin-panel/safety/checklist/
"""

from rest_framework import serializers

from apps.safety.models import (
    SafetyCheckItem,
    SafetyCheckSection,
    SafetyChecklistRevision,
)


class ChecklistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SafetyCheckItem
        fields = ["id", "title", "description", "is_required", "order"]


class ChecklistSectionSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = SafetyCheckSection
        fields = ["id", "name", "description", "order", "items", "item_count"]

    def get_items(self, obj):
        qs = obj.items.filter(is_active=True).order_by("order", "id")
        return ChecklistItemSerializer(qs, many=True).data

    def get_item_count(self, obj):
        return obj.items.filter(is_active=True).count()


class ChecklistSectionCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(
        max_length=1000, allow_blank=True, required=False, default=""
    )


class ChecklistSectionUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(
        max_length=1000, allow_blank=True, required=False
    )


class ChecklistItemCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(
        max_length=1000, allow_blank=True, required=False, default=""
    )
    is_required = serializers.BooleanField(required=False, default=True)


class ChecklistItemUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(
        max_length=1000, allow_blank=True, required=False
    )
    is_required = serializers.BooleanField(required=False)


class ChecklistReorderSerializer(serializers.Serializer):
    ordered_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )


class ChecklistItemReorderSerializer(serializers.Serializer):
    section_id = serializers.IntegerField(min_value=1)
    ordered_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )


class ChecklistStateSerializer(serializers.Serializer):
    facility_id = serializers.IntegerField()
    last_published_at = serializers.DateTimeField(allow_null=True)
    last_published_by = serializers.CharField(allow_null=True)
    last_version = serializers.IntegerField(allow_null=True)
    has_unpublished_changes = serializers.BooleanField()


class RevisionListItemSerializer(serializers.ModelSerializer):
    published_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SafetyChecklistRevision
        fields = ["id", "version", "published_at", "published_by_name", "is_active"]

    def get_published_by_name(self, obj):
        user = obj.published_by
        if user is None:
            return None
        return getattr(user, "name", None) or user.get_username()


class RevisionDetailSerializer(serializers.ModelSerializer):
    published_by_name = serializers.SerializerMethodField()
    change_summary = serializers.SerializerMethodField()

    class Meta:
        model = SafetyChecklistRevision
        fields = [
            "id",
            "version",
            "published_at",
            "published_by_name",
            "is_active",
            "revision_data",
            "change_summary",
        ]

    def get_published_by_name(self, obj):
        user = obj.published_by
        if user is None:
            return None
        return getattr(user, "name", None) or user.get_username()

    def get_change_summary(self, obj):
        from apps.safety.selectors.checklist import compute_change_summary

        return compute_change_summary(obj)
