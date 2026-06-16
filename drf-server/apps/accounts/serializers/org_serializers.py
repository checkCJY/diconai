"""
apps/accounts/serializers/org_serializers.py
조직 관리 API 시리얼라이저
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.models import Department, Company

User = get_user_model()


# ── 조직도 트리 ────────────────────────────────────────────────────────────


class DeptTreeItemSerializer(serializers.ModelSerializer):
    leader_name = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    def get_leader_name(self, obj):
        return obj.leader.name if obj.leader else None

    def get_children(self, obj):
        children = [
            d for d in self.context.get("all_depts", []) if d.parent_id == obj.id
        ]
        return DeptTreeItemSerializer(children, many=True, context=self.context).data

    class Meta:
        model = Department
        fields = ["id", "name", "code", "parent_id", "company_id", "leader_id", "leader_name", "children"]


class CompanyTreeSerializer(serializers.ModelSerializer):
    departments = serializers.SerializerMethodField()

    def get_departments(self, obj):
        all_depts = self.context.get("all_depts", [])
        root_depts = [
            d for d in all_depts if d.company_id == obj.id and d.parent_id is None
        ]
        return DeptTreeItemSerializer(root_depts, many=True, context=self.context).data

    class Meta:
        model = Company
        fields = ["id", "name", "departments"]


# ── 부서 상세 ──────────────────────────────────────────────────────────────


class DeptDetailSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", default=None)
    leader_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()

    def get_leader_name(self, obj):
        return obj.leader.name if obj.leader else None

    def get_updated_by_name(self, obj):
        return obj.updated_by.name if obj.updated_by else None

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "code",
            "company_id",
            "company_name",
            "parent_id",
            "leader_id",
            "leader_name",
            "created_at",
            "updated_at",
            "updated_by_name",
        ]


# ── 부서 생성 / 수정 ───────────────────────────────────────────────────────


class DeptCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["name", "code", "company", "parent"]
        extra_kwargs = {
            "company": {"required": False},
            "parent": {"required": False},
        }


class DeptUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["name", "code"]
        extra_kwargs = {
            "name": {"required": False},
            "code": {"required": False},
        }


# ── 구성원 목록 ────────────────────────────────────────────────────────────


class MemberListSerializer(serializers.ModelSerializer):
    position = serializers.CharField(source="position.name", default=None)
    status = serializers.SerializerMethodField()
    is_leader = serializers.SerializerMethodField()

    def get_status(self, obj):
        if not obj.is_active:
            return "inactive"
        if obj.is_locked:
            return "locked"
        return "active"

    def get_is_leader(self, obj):
        dept_id = self.context.get("dept_id")
        if not dept_id:
            return False
        return Department.objects.filter(id=dept_id, leader_id=obj.id).exists()

    class Meta:
        model = User
        fields = ["id", "name", "username", "position", "status", "is_leader"]
